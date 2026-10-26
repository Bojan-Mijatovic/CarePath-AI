"""Faza 0: brzi test lokalnih modela (brzina, italijanski, tool calling).

Pokretanje: .venv\\Scripts\\python.exe testing\\llm_bench.py qwen2.5:7b qwen2.5:14b
"""

import sys
import time

import ollama

ITALIAN_PROMPT = (
    "Scrivi in italiano, in 3 frasi, una nota per il medico di medicina generale: "
    "la paziente Maria R., 81 anni, scompenso cardiaco, non ritira il furosemide da 30 giorni "
    "e l'HbA1c è in ritardo. Il Centro Servizi ha organizzato la consegna a domicilio."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "wait_by_hospital",
            "description": "Attesa media in giorni per uno step del percorso, per ospedale.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pathway_id": {"type": "string"},
                    "step": {"type": "string", "enum": ["cardio_visit", "echo", "lab_bnp"]},
                    "period_days": {"type": "integer"},
                },
                "required": ["pathway_id", "step"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "free_slots",
            "description": "Posti liberi per un servizio nelle prossime settimane, per ASST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service": {"type": "string"},
                    "horizon_days": {"type": "integer"},
                },
                "required": ["service"],
            },
        },
    },
]

TOOL_PROMPT = (
    "Percorso hf_lombardia_v1. Perché l'attesa per l'ecocardiografia all'Ospedale B è così lunga? "
    "Usa gli strumenti, non inventare numeri."
)

OPTIONS = {"temperature": 0, "seed": 42}


def tokens_per_second(resp) -> float:
    return resp["eval_count"] / (resp["eval_duration"] / 1e9) if resp.get("eval_duration") else 0.0


def bench(model: str) -> None:
    print(f"\n=== {model} ===")
    ollama.chat(model=model, messages=[{"role": "user", "content": "ciao"}], options=OPTIONS)  # warm-up

    t0 = time.perf_counter()
    resp = ollama.chat(model=model, messages=[{"role": "user", "content": ITALIAN_PROMPT}], options=OPTIONS)
    print(f"italiano: {time.perf_counter() - t0:.1f} s, {tokens_per_second(resp):.1f} tok/s")
    print("  " + resp["message"]["content"].strip().replace("\n", "\n  "))

    t0 = time.perf_counter()
    resp = ollama.chat(model=model, messages=[{"role": "user", "content": TOOL_PROMPT}], tools=TOOLS, options=OPTIONS)
    calls = resp["message"].get("tool_calls") or []
    print(f"tool calling: {time.perf_counter() - t0:.1f} s, {len(calls)} poziva")
    for c in calls:
        print(f"  {c['function']['name']}({dict(c['function']['arguments'])})")


if __name__ == "__main__":
    for m in sys.argv[1:] or ["qwen2.5:7b"]:
        bench(m)
