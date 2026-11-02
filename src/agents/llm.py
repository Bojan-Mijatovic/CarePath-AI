"""LLM gateway: the one way agents call a model (SPEC §8; delivery plan step 2.7).

`complete(agent, prompt_version, messages, *, tools, schema, model)` sends a chat to Ollama with
temperature 0, a fixed seed and thinking off, or answers from the cache in demo/cache/. A `schema` is a
Pydantic model: its JSON schema goes to Ollama's structured output and the answer is validated against it;
an invalid answer gets one retry that tells the model what was wrong (at temperature 0 the same messages
would give the same answer). Every call writes one JSON line to logs/llm.jsonl.

Modes (SPEC §8): `live` calls the model and stores the answer (warm-up, 600 s timeout); `cache_first`
answers from the cache and calls on a miss (development, rehearsals; 20 s); `cache_only` never calls a
model (the demo starts in it, D14). When no answer can be had, `complete` raises LLMUnavailable
(CacheMiss, LLMTimeout, LLMInvalid) and the agent uses its template (D17); the Investigator has no
template, which is what the cache completeness check guards (C10).
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
import ollama
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "demo" / "cache"
LOG_PATH = ROOT / "logs" / "llm.jsonl"
LARGE, SMALL = "qwen3:30b-instruct", "qwen3:4b-instruct"  # D11: cached outputs, short live text
MODELS = (LARGE, SMALL)
SEED = 42
DEMO_TIMEOUT_S, WARMUP_TIMEOUT_S = 20, 600
KEEP_ALIVE = "30m"  # the model in use stays loaded between calls
NUM_CTX = 8192  # Ollama's default of 4096 cut the Investigator's prompt: 8 tool schemas alone are ~3,000 tokens
Mode = Literal["live", "cache_first", "cache_only"]
MODES = ("live", "cache_first", "cache_only")


class LLMUnavailable(Exception):
    """No valid answer: the agent falls back to its template."""


class CacheMiss(LLMUnavailable):
    pass


class LLMTimeout(LLMUnavailable):
    pass


class LLMInvalid(LLMUnavailable):
    pass


@dataclass
class GatewayResult:
    message: dict  # the assistant message: content, and tool_calls when tools were given
    data: BaseModel | None  # the validated answer when a schema was given
    key: str
    cache_hit: bool
    retries: int = 0
    latency_ms: float = 0.0
    extra: dict = field(default_factory=dict)

    @property
    def content(self) -> str:
        return self.message.get("content") or ""


def canonical(obj) -> str:
    """SPEC §8: keys sorted, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def cache_key(agent: str, model: str, prompt_version: str, messages: list, tools: list | None, schema: dict | None) -> str:
    request = {"agent": agent, "model": model, "prompt_version": prompt_version, "messages": messages,
               "tools": tools, "schema": schema}
    return hashlib.sha256(canonical(request).encode("utf-8")).hexdigest()


def _as_dict(obj) -> dict:
    return obj.model_dump(exclude_none=True) if hasattr(obj, "model_dump") else dict(obj)


class Gateway:
    def __init__(self, mode: Mode = "cache_only", cache_dir: Path = CACHE_DIR, log_path: Path | None = LOG_PATH,
                 client=None, timeout_s: float | None = None, host: str | None = None):
        self.cache_dir, self.log_path = cache_dir, log_path
        self.timeout_s = timeout_s
        self._injected, self._client, self._host = client, None, host
        self.mode: Mode = "cache_only"
        self.set_mode(mode)

    def set_mode(self, mode: Mode) -> None:
        if mode not in MODES:
            raise ValueError(f"mode is one of {MODES}")
        self.mode = mode
        self._client = None  # the timeout depends on the mode

    def client(self):
        if self._injected is not None:
            return self._injected
        if self._client is None:  # warm-up waits 600 s, the demo 20 s
            self._client = ollama.Client(host=self._host, timeout=self.timeout())
        return self._client

    def timeout(self) -> float:
        return self.timeout_s or (WARMUP_TIMEOUT_S if self.mode == "live" else DEMO_TIMEOUT_S)

    def complete(self, agent: str, prompt_version: str, messages: list[dict], *, tools: list | None = None,
                 schema: type[BaseModel] | None = None, model: str) -> GatewayResult:
        if model not in MODELS:
            raise ValueError(f"model {model!r} is not one of {MODELS} (D11)")
        json_schema = schema.model_json_schema() if schema else None
        key = cache_key(agent, model, prompt_version, messages, tools, json_schema)
        path = self.cache_dir / agent / f"{key}.json"
        started = time.perf_counter()
        log = {"agent": agent, "model": model, "prompt_version": prompt_version, "key": key, "mode": self.mode}
        try:
            if self.mode != "live" and path.is_file():
                message = json.loads(path.read_text(encoding="utf-8"))["response"]
                result = GatewayResult(message, self._validate(message, schema), key, cache_hit=True)
            elif self.mode == "cache_only":
                raise CacheMiss(f"{agent}: no cached answer for {key[:12]} (cache_only)")
            else:
                result = self._call(agent, model, messages, tools, schema, json_schema, key)
                self._store(path, agent, model, prompt_version, messages, tools, json_schema, result.message)
        except LLMUnavailable as e:
            self._log(log | {"cache_hit": False, "valid": False, "retries": 0, "error": type(e).__name__}, started)
            raise
        result.latency_ms = (time.perf_counter() - started) * 1000
        self._log(log | {"cache_hit": result.cache_hit, "valid": True, "retries": result.retries}, started)
        return result

    def _call(self, agent, model, messages, tools, schema, json_schema, key) -> GatewayResult:
        conversation = list(messages)
        for attempt in range(2):  # the answer, then one retry (SPEC §8)
            try:
                response = self.client().chat(model=model, messages=conversation, tools=tools, format=json_schema,
                                              options={"temperature": 0, "seed": SEED, "num_ctx": NUM_CTX}, think=False,
                                              keep_alive=KEEP_ALIVE)
            except (httpx.TimeoutException, TimeoutError) as e:
                raise LLMTimeout(f"{agent}: {model} gave no answer in {self.timeout():.0f} s") from e
            except (httpx.HTTPError, ConnectionError, ollama.ResponseError) as e:
                raise LLMUnavailable(f"{agent}: {model} is not reachable: {e}") from e
            message = _as_dict(response["message"])
            try:
                return GatewayResult(message, self._validate(message, schema), key, cache_hit=False, retries=attempt)
            except LLMInvalid as e:
                conversation = list(messages) + [
                    message, {"role": "user", "content": f"La risposta non rispetta lo schema JSON richiesto: {e}. "
                                                         "Rispondi di nuovo solo con JSON valido secondo lo schema."}]
                error = e
        raise LLMInvalid(f"{agent}: invalid answer twice: {error}")

    @staticmethod
    def _validate(message: dict, schema: type[BaseModel] | None) -> BaseModel | None:
        if schema is None:
            return None
        try:
            return schema.model_validate_json(message.get("content") or "")
        except ValidationError as e:
            raise LLMInvalid(str(e).splitlines()[0]) from e

    def _store(self, path, agent, model, prompt_version, messages, tools, json_schema, message) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"agent": agent, "model": model, "prompt_version": prompt_version,
                 "request": {"messages": messages, "tools": tools, "schema": json_schema}, "response": message}
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    def _log(self, line: dict, started: float) -> None:
        if self.log_path is None:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        line = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **line,
                "latency_ms": round((time.perf_counter() - started) * 1000)}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(canonical(line) + "\n")


_gateway = Gateway()


def configure(**kwargs) -> Gateway:
    """Replace the process's gateway, for example Gateway(mode="live") in a warm-up run."""
    global _gateway
    _gateway = Gateway(**kwargs)
    return _gateway


def set_mode(mode: Mode) -> None:
    """The operator's cache-only switch (step 2.20)."""
    _gateway.set_mode(mode)


def mode() -> Mode:
    return _gateway.mode


def complete(agent: str, prompt_version: str, messages: list[dict], *, tools: list | None = None,
             schema: type[BaseModel] | None = None, model: str) -> GatewayResult:
    """SPEC §8: the one function every agent calls."""
    return _gateway.complete(agent, prompt_version, messages, tools=tools, schema=schema, model=model)
