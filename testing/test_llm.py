"""LLM gateway (delivery plan step 2.7, SPEC §8): hit, miss, timeout and invalid JSON, without a model.

The last test calls the real qwen3:4b-instruct through Ollama; it runs only with CAREPATH_LIVE_LLM=1.
"""

import json
import os

import httpx
import pytest
from pydantic import BaseModel

from agents import llm

MESSAGES = [{"role": "user", "content": "Riassumi."}]


class Summary(BaseModel):
    text: str
    patients: int


class FakeClient:
    """Answers with the given contents in turn, or raises; records every call."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return {"message": {"role": "assistant", "content": answer}}


def gateway(tmp_path, mode, client):
    return llm.Gateway(mode=mode, cache_dir=tmp_path / "cache", log_path=tmp_path / "llm.jsonl", client=client)


def log_lines(tmp_path):
    return [json.loads(line) for line in (tmp_path / "llm.jsonl").read_text(encoding="utf-8").splitlines()]


def complete(g, **kw):
    return g.complete("reporter", "v1", MESSAGES, schema=Summary, model=llm.LARGE, **kw)


def test_miss_calls_the_model_and_the_next_call_hits_the_cache(tmp_path):
    client = FakeClient('{"text": "Tutto bene", "patients": 3}')
    first = complete(gateway(tmp_path, "cache_first", client))
    assert (first.cache_hit, first.data) == (False, Summary(text="Tutto bene", patients=3))
    call = client.calls[0]
    assert call["options"] == {"temperature": 0, "seed": llm.SEED, "num_ctx": llm.NUM_CTX}
    assert call["think"] is False
    assert call["format"] == Summary.model_json_schema()
    second = complete(gateway(tmp_path, "cache_only", FakeClient()))  # no answer left: it must not call
    assert (second.cache_hit, second.data, second.key) == (True, first.data, first.key)
    stored = json.loads(next((tmp_path / "cache" / "reporter").glob("*.json")).read_text(encoding="utf-8"))
    assert stored["prompt_version"] == "v1"
    assert stored["request"]["messages"] == MESSAGES
    assert [(line["mode"], line["cache_hit"], line["valid"]) for line in log_lines(tmp_path)] == [
        ("cache_first", False, True), ("cache_only", True, True)]
    assert set(log_lines(tmp_path)[0]) == {"ts", "agent", "model", "prompt_version", "key", "mode", "cache_hit",
                                          "latency_ms", "valid", "retries"}


def test_cache_only_miss_raises_for_the_template(tmp_path):
    with pytest.raises(llm.CacheMiss):
        complete(gateway(tmp_path, "cache_only", FakeClient()))
    assert log_lines(tmp_path)[0]["error"] == "CacheMiss"


def test_timeout_raises(tmp_path):
    with pytest.raises(llm.LLMTimeout):
        complete(gateway(tmp_path, "cache_first", FakeClient(httpx.ReadTimeout("slow"))))
    assert not (tmp_path / "cache").exists()  # nothing cached


def test_invalid_json_gets_one_retry_that_says_what_was_wrong(tmp_path):
    client = FakeClient("non è JSON", '{"text": "Ok", "patients": 1}')
    result = complete(gateway(tmp_path, "live", client))
    assert (result.retries, result.data.patients) == (1, 1)
    retry = client.calls[1]["messages"]
    assert retry[:1] == MESSAGES
    assert retry[-1]["role"] == "user"
    assert "schema" in retry[-1]["content"]


def test_invalid_twice_raises_and_caches_nothing(tmp_path):
    with pytest.raises(llm.LLMInvalid):
        complete(gateway(tmp_path, "live", FakeClient('{"text": 1}', '{"patients": "tre"}')))
    assert not (tmp_path / "cache").exists()


def test_live_calls_again_and_overwrites(tmp_path):
    complete(gateway(tmp_path, "live", FakeClient('{"text": "a", "patients": 1}')))
    again = complete(gateway(tmp_path, "live", FakeClient('{"text": "b", "patients": 2}')))
    assert (again.cache_hit, again.data.text) == (False, "b")
    assert complete(gateway(tmp_path, "cache_only", FakeClient())).data.text == "b"


def test_key_changes_with_the_prompt_version_and_the_input(tmp_path):
    key = llm.cache_key("reporter", llm.LARGE, "v1", MESSAGES, None, None)
    assert key != llm.cache_key("reporter", llm.LARGE, "v2", MESSAGES, None, None)
    assert key != llm.cache_key("reporter", llm.LARGE, "v1", [{"role": "user", "content": "Riassumi!"}], None, None)
    assert key == llm.cache_key("reporter", llm.LARGE, "v1", [{"content": "Riassumi.", "role": "user"}], None, None)


def test_only_the_d11_models_and_known_modes(tmp_path):
    with pytest.raises(ValueError):
        gateway(tmp_path, "cache_first", FakeClient()).complete("reporter", "v1", MESSAGES, model="qwen3:30b")
    with pytest.raises(ValueError):
        llm.Gateway(mode="offline")
    assert llm.Gateway().mode == "cache_only"  # the demo starts in cache_only (D14)
    assert (llm.Gateway(mode="live").timeout(), llm.Gateway(mode="cache_first").timeout()) == (600, 20)


def test_tool_calls_pass_through_without_a_schema(tmp_path):
    class ToolClient(FakeClient):
        def chat(self, **kwargs):
            self.calls.append(kwargs)
            return {"message": {"role": "assistant", "content": "",
                                "tool_calls": [{"function": {"name": "free_slots", "arguments": {"service": "echo"}}}]}}
    tools = [{"type": "function", "function": {"name": "free_slots", "parameters": {"type": "object"}}}]
    result = gateway(tmp_path, "cache_first", ToolClient()).complete("investigator", "v1", MESSAGES, tools=tools,
                                                                     model=llm.LARGE)
    assert result.data is None
    assert result.message["tool_calls"][0]["function"]["name"] == "free_slots"


@pytest.mark.skipif(os.environ.get("CAREPATH_LIVE_LLM") != "1", reason="calls Ollama; set CAREPATH_LIVE_LLM=1")
def test_live_ollama_answers_in_the_schema(tmp_path):
    g = llm.Gateway(mode="live", cache_dir=tmp_path / "cache", log_path=tmp_path / "llm.jsonl")
    messages = [{"role": "user", "content": "In un paese ci sono 3 pazienti. Rispondi in JSON con text (una frase "
                                            "in italiano) e patients (il numero)."}]
    result = g.complete("reporter", "smoke", messages, schema=Summary, model=llm.SMALL)
    assert result.data.patients == 3
    assert llm.Gateway(mode="cache_only", cache_dir=tmp_path / "cache", log_path=None).complete(
        "reporter", "smoke", messages, schema=Summary, model=llm.SMALL).data == result.data
