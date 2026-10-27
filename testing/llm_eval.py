"""Faza 0, korak 0.4: evaluacija lokalnih modela za CarePath.

Tri testa po modelu, temperatura 0, seed 42, thinking iskljucen gde postoji:
  1. italiano    5 tekstova iz cinjenica koje daje kod; automatska provera cinjenica
  2. tools       5 pitanja, jedan poziv alata; provera imena, sema i argumenata
  3. investigate istraga u vise koraka sa laznim rezultatima alata (kao Investigator, AC5)

Pokretanje: uv run python testing\\llm_eval.py qwen3:30b-instruct qwen3:4b-instruct
Rezultati: testing/results/<model>.json
"""

import json
import re
import sys
import time
from pathlib import Path

import ollama

OPTIONS = {"temperature": 0, "seed": 42, "num_predict": 400}
RESULTS_DIR = Path(__file__).parent / "results"

# --- alati iz odeljka 7 Solution Plana -----------------------------------------------------------

STEPS = ["discharge", "telemon", "cardio_visit", "echo", "lab_bnp"]
ASSTS = ["asst_mantova", "asst_cremona", "asst_crema"]
SERVICES = ["echo", "cardio_visit", "lab"]
GROUPINGS = ["mmg", "mmg_group", "comune", "age_band"]


def tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


PATHWAY = {"type": "string", "description": "ID del percorso, es. hf_lombardia_v1"}
TOOLS = [
    tool("compliance_by_step", "Quota di pazienti che completano ogni step del percorso in tempo.",
         {"pathway_id": PATHWAY, "asst": {"type": "string", "enum": ASSTS}}, ["pathway_id"]),
    tool("wait_by_hospital", "Attesa media in giorni per uno step del percorso, per ospedale.",
         {"pathway_id": PATHWAY, "step": {"type": "string", "enum": STEPS},
          "period_days": {"type": "integer"}}, ["pathway_id", "step"]),
    tool("patients_overdue", "Pazienti con la scadenza di uno step superata.",
         {"pathway_id": PATHWAY, "step": {"type": "string", "enum": STEPS},
          "asst": {"type": "string", "enum": ASSTS}, "limit": {"type": "integer"}}, ["pathway_id", "step"]),
    tool("free_slots", "Posti liberi per un servizio, per ospedale, nei prossimi giorni.",
         {"service": {"type": "string", "enum": SERVICES}, "asst": {"type": "string", "enum": ASSTS},
          "horizon_days": {"type": "integer"}}, ["service"]),
    tool("adherence_by_group", "Ritiro dei farmaci in farmacia per gruppo di pazienti.",
         {"pathway_id": PATHWAY,
          "grouping": {"type": "string", "enum": GROUPINGS,
                       "description": "mmg = singolo medico; mmg_group = gruppo o cooperativa di MMG; "
                                      "comune = comune di residenza; age_band = fascia di eta'"},
          "period_days": {"type": "integer"}}, ["pathway_id", "grouping"]),
    tool("readmissions_by_comune", "Riammissioni a 30 giorni per comune.",
         {"pathway_id": PATHWAY, "period_days": {"type": "integer"}}, ["pathway_id"]),
    tool("risk_drivers", "Principali fattori di rischio per un segmento di pazienti.",
         {"pathway_id": PATHWAY, "segment": {"type": "string"}}, ["pathway_id"]),
]
SCHEMAS = {t["function"]["name"]: t["function"]["parameters"] for t in TOOLS}

SYSTEM_TOOLS = (
    "Sei un analista di CarePath per l'ATS della Val Padana. Rispondi usando solo gli strumenti. "
    "Non inventare numeri. Usa solo i parametri definiti negli strumenti."
)

# --- casi di test ---------------------------------------------------------------------------------

ITALIAN_CASES = [
    {
        "id": "nota_mmg_maria",
        "prompt": "Scrivi in italiano, in 3 frasi, una nota per il medico di medicina generale. Fatti: "
                  "paziente Maria R., 81 anni, scompenso cardiaco; NON ritira il furosemide da 30 giorni; "
                  "l'HbA1c e' in ritardo; il Centro Servizi ha organizzato la consegna a domicilio.",
        "must": [r"furosemide", r"30", r"domicili", r"non (ha )?(ancora )?ritira|mancato ritiro|non .{0,20}ritirat"],
        "must_not": [r"continua a (prendere|assumere)", r"senza interruzion", r"regolarmente"],
    },
    {
        "id": "allarme_eco",
        "prompt": "Scrivi in italiano, in 2 frasi, il testo di un allarme per la direzione ATS. Fatti: "
                  "attesa per ecocardiografia all'Ospedale B: 41 giorni; soglia PDTA: 30 giorni; "
                  "pazienti coinvolti: 46.",
        "must": [r"41", r"30", r"46", r"Ospedale B"],
        "must_not": [r"Ospedale [AC]"],
    },
    {
        "id": "script_chiamata",
        "prompt": "Scrivi in italiano, in 3 frasi, cosa dice l'operatore del Centro Servizi al telefono. Fatti: "
                  "paziente Luigi P.; la sua ecocardiografia era prevista tra 41 giorni all'Ospedale B; "
                  "e' stata spostata all'Ospedale C tra 4 giorni; il medico di base e' gia' informato.",
        "must": [r"Ospedale C", r"\b4\b|quattro"],
        "must_not": [r"Ospedale B tra 4|tra 4 giorni all'Ospedale B"],
    },
    {
        "id": "proposta_regola",
        "prompt": "Scrivi in italiano, in una frase, una proposta di regola per la direzione. Fatti: se un "
                  "paziente non ritira il furosemide per 30 giorni, avvisare il MMG e inserirlo nella lista "
                  "chiamate del Centro Servizi.",
        "must": [r"furosemide", r"30|un mese", r"MMG|medico", r"lista|chiamat"],
        "must_not": [r"Maggiore Grado"],
    },
    {
        "id": "report_pne",
        "prompt": "Scrivi in italiano, in 2 frasi, per il report mensile. Fatti: riammissioni a 30 giorni per "
                  "scompenso 13,8%; obiettivo ATS al massimo 12% (quindi siamo SOPRA l'obiettivo); aderenza al "
                  "PAI 58%, scesa di 6 punti in 3 settimane.",
        "must": [r"13[,.]8", r"12", r"58", r"\b6\b|sei"],
        "must_not": [r"(sotto|inferiore|entro|raggiunto).{0,25}(obiettivo|target|12)"],
    },
]

TOOL_CASES = [
    {"id": "attesa_eco", "q": "Qual e' l'attesa media per l'ecocardiografia per ospedale negli ultimi 90 giorni? "
                              "Percorso hf_lombardia_v1.",
     "name": "wait_by_hospital", "args": {"pathway_id": "hf_lombardia_v1", "step": "echo"}},
    {"id": "posti_crema", "q": "Quanti posti liberi per ecocardiografia ci sono nelle prossime 3 settimane "
                               "nell'ASST Crema?",
     "name": "free_slots", "args": {"service": "echo", "asst": "asst_crema"}},
    {"id": "ritiro_mmg", "q": "Confronta il ritiro dei farmaci per gruppo di MMG negli ultimi 60 giorni, "
                              "percorso hf_lombardia_v1.",
     "name": "adherence_by_group", "args": {"pathway_id": "hf_lombardia_v1", "grouping": "mmg_group"}},
    {"id": "riammissioni", "q": "Quali comuni hanno piu' riammissioni a 30 giorni negli ultimi 6 mesi? "
                                "Percorso hf_lombardia_v1.",
     "name": "readmissions_by_comune", "args": {"pathway_id": "hf_lombardia_v1"}},
    {"id": "scaduti", "q": "Elenca i 20 pazienti con la visita cardiologica scaduta nell'ASST Mantova, "
                           "percorso hf_lombardia_v1.",
     "name": "patients_overdue",
     "args": {"pathway_id": "hf_lombardia_v1", "step": "cardio_visit", "asst": "asst_mantova", "limit": 20}},
]

FAKE_RESULTS = {
    "wait_by_hospital": {"unit": "giorni", "Ospedale A": 22, "Ospedale B": 41, "Ospedale C": 14},
    "free_slots": {"horizon_days": 21, "Ospedale A": 6, "Ospedale B": 0, "Ospedale C": 34},
    "adherence_by_group": {"metric": "ritiro furosemide", "Cooperativa 3": 0.52, "resto ATS": 0.81},
    "risk_drivers": {"drivers": ["furosemide non ritirato", "eco in ritardo > 30 giorni", "distanza > 40 km"]},
    "compliance_by_step": {"echo": 0.48, "cardio_visit": 0.71, "telemon": 0.66},
    "readmissions_by_comune": {"Sermide e Felonica": 0.19, "Poggio Rusco": 0.17, "Ostiglia": 0.16},
    "patients_overdue": {"count": 46, "sample": ["p_04512", "p_01877"]},
}

INVESTIGATION_Q = (
    "Allarme: l'attesa per l'ecocardiografia all'Ospedale B e' di 41 giorni, oltre la soglia PDTA di 30. "
    "Percorso hf_lombardia_v1. Indaga le cause usando gli strumenti: confronta gli ospedali, cerca posti "
    "liberi per l'ecocardiografia, controlla il ritiro dei farmaci per gruppo di MMG e i fattori di rischio. "
    "Quando hai abbastanza dati, smetti di chiamare strumenti."
)
FINAL_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"}, "strumento": {"type": "string"}},
            "required": ["testo", "strumento"]}},
        "conclusione": {"type": "string"},
    },
    "required": ["claims", "conclusione"],
}
INVESTIGATION_FACTS = [r"41", r"34", r"52", r"Ospedale C"]
# v2: asks for every relevant number, including where capacity is free. v1 ("riassumi in JSON") let
# 6 of 7 models drop Ospedale C's free slots, the finding the reschedule action depends on.
FINAL_PROMPT = (
    "Ora riassumi in JSON. Per ogni strumento che hai chiamato scrivi un'affermazione con tutti i numeri "
    "rilevanti che ha restituito, compresi gli ospedali con posti liberi verso cui spostare i pazienti, e "
    "indica lo strumento. Poi una conclusione in italiano con l'azione proposta."
)
FINAL_NUM_PREDICT = 1200

# --- pomocne funkcije -----------------------------------------------------------------------------


def chat(model, messages, final=False, **kw):
    """ollama.chat sa thinking iskljucenim kad model to podrzava."""
    options = {**OPTIONS, "num_predict": FINAL_NUM_PREDICT} if final else OPTIONS
    try:
        return ollama.chat(model=model, messages=messages, options=options, think=False, **kw)
    except ollama.ResponseError as e:
        if "think" not in str(e).lower():
            raise
        return ollama.chat(model=model, messages=messages, options=options, **kw)


def rates(resp):
    pe = resp.prompt_eval_count or 0
    ped = (resp.prompt_eval_duration or 0) / 1e9
    ev = resp.eval_count or 0
    evd = (resp.eval_duration or 0) / 1e9
    return {"prompt_tok": pe, "prefill_tps": round(pe / ped, 1) if ped else None,
            "out_tok": ev, "decode_tps": round(ev / evd, 1) if evd else None}


def schema_errors(name, args):
    schema = SCHEMAS.get(name)
    if schema is None:
        return [f"nepoznat alat {name}"]
    errs = [f"nepoznat argument {k}" for k in args if k not in schema["properties"]]
    errs += [f"nedostaje {k}" for k in schema["required"] if k not in args]
    for k, v in args.items():
        enum = schema["properties"].get(k, {}).get("enum")
        if enum and v not in enum:
            errs.append(f"{k}={v!r} nije u {enum}")
    return errs


# --- testovi --------------------------------------------------------------------------------------


def run_italian(model):
    out = []
    for case in ITALIAN_CASES:
        t0 = time.perf_counter()
        resp = chat(model, [{"role": "user", "content": case["prompt"]}])
        text = resp.message.content.strip()
        missing = [p for p in case["must"] if not re.search(p, text, re.I)]
        wrong = [p for p in case["must_not"] if re.search(p, text, re.I)]
        truncated = (resp.eval_count or 0) >= OPTIONS["num_predict"]
        out.append({"id": case["id"], "ok": not missing and not wrong and not truncated, "missing": missing,
                    "wrong": wrong, "truncated": truncated,
                    "seconds": round(time.perf_counter() - t0, 1), **rates(resp), "text": text})
    return out


def run_tools(model):
    out = []
    for case in TOOL_CASES:
        t0 = time.perf_counter()
        resp = chat(model, [{"role": "system", "content": SYSTEM_TOOLS}, {"role": "user", "content": case["q"]}],
                    tools=TOOLS)
        calls = [{"name": c.function.name, "args": dict(c.function.arguments)} for c in resp.message.tool_calls or []]
        first = calls[0] if calls else None
        errs = schema_errors(first["name"], first["args"]) if first else ["nema poziva"]
        right_name = bool(first) and first["name"] == case["name"]
        arg_diff = {k: (first["args"].get(k) if first else None, v) for k, v in case["args"].items()
                    if not first or first["args"].get(k) != v}
        out.append({"id": case["id"], "ok": right_name and not errs and not arg_diff,
                    "right_name": right_name, "schema_errors": errs, "arg_diff": arg_diff, "calls": calls,
                    "seconds": round(time.perf_counter() - t0, 1), **rates(resp)})
    return out


def run_investigation(model, max_turns=6):
    messages = [{"role": "system", "content": SYSTEM_TOOLS}, {"role": "user", "content": INVESTIGATION_Q}]
    trace, t0 = [], time.perf_counter()
    for _ in range(max_turns):
        resp = chat(model, messages, tools=TOOLS)
        calls = resp.message.tool_calls or []
        if not calls:
            break
        messages.append(resp.message)
        for c in calls:
            name, args = c.function.name, dict(c.function.arguments)
            trace.append({"name": name, "args": args, "schema_errors": schema_errors(name, args)})
            result = FAKE_RESULTS.get(name, {"errore": "strumento sconosciuto"})
            messages.append({"role": "tool", "content": json.dumps(result, ensure_ascii=False), "tool_name": name})
    messages.append({"role": "user", "content": FINAL_PROMPT})
    final = chat(model, messages, format=FINAL_SCHEMA, final=True)
    seconds = round(time.perf_counter() - t0, 1)
    try:
        answer = json.loads(final.message.content)
        valid = True
    except json.JSONDecodeError:
        answer, valid = final.message.content, False
    blob = json.dumps(answer, ensure_ascii=False)
    missing = [p for p in INVESTIGATION_FACTS if not re.search(p, blob)]
    tools_used = sorted({t["name"] for t in trace})
    return {"ok": valid and not missing and len(tools_used) >= 3, "seconds": seconds, "valid_json": valid,
            "tools_used": tools_used, "tool_calls": len(trace),
            "schema_errors": [e for t in trace for e in t["schema_errors"]],
            "missing_facts": missing, "trace": trace, "answer": answer}


def evaluate(model):
    print(f"\n=== {model} ===", flush=True)
    t0 = time.perf_counter()
    chat(model, [{"role": "user", "content": "ciao"}])  # ucitavanje modela u memoriju, ne meri se
    load = round(time.perf_counter() - t0, 1)

    italian = run_italian(model)
    print(f"italiano:    {sum(c['ok'] for c in italian)}/5 tacno, "
          f"prosek {sum(c['seconds'] for c in italian) / 5:.1f} s", flush=True)
    for c in italian:
        if not c["ok"]:
            note = " ODSECENO: model verovatno razmislja umesto da odgovori" if c["truncated"] else ""
            print(f"  - {c['id']}: nedostaje {c['missing']} pogresno {c['wrong']}{note}")

    tools = run_tools(model)
    print(f"tools:       {sum(c['ok'] for c in tools)}/5 tacno, "
          f"prosek {sum(c['seconds'] for c in tools) / 5:.1f} s", flush=True)
    for c in tools:
        if not c["ok"]:
            print(f"  - {c['id']}: {c['calls']} sema {c['schema_errors']} razlika {c['arg_diff']}")

    inv = run_investigation(model)
    print(f"investigate: {'OK' if inv['ok'] else 'NE'}, {inv['seconds']} s, alati {inv['tools_used']}, "
          f"nedostaje {inv['missing_facts']}, greske seme {len(inv['schema_errors'])}", flush=True)

    decode = [c["decode_tps"] for c in italian if c["decode_tps"]]
    summary = {"model": model, "load_s": load,
               "decode_tps": round(sum(decode) / len(decode), 1) if decode else None,
               "italian_ok": sum(c["ok"] for c in italian), "tools_ok": sum(c["ok"] for c in tools),
               "investigation_ok": inv["ok"], "investigation_s": inv["seconds"]}
    print(f"sazetak:     {summary}", flush=True)

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{model.replace(':', '_').replace('/', '_')}.json"
    path.write_text(json.dumps({"summary": summary, "italian": italian, "tools": tools, "investigation": inv},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    ollama.generate(model=model, prompt="", keep_alive=0)  # oslobodi RAM pre sledeceg modela


def evaluate_investigation_only(model):
    print(f"\n=== {model} (samo istraga) ===", flush=True)
    chat(model, [{"role": "user", "content": "ciao"}])
    inv = run_investigation(model)
    print(f"investigate: {'OK' if inv['ok'] else 'NE'}, {inv['seconds']} s, alati {inv['tools_used']}, "
          f"nedostaje {inv['missing_facts']}, greske seme {len(inv['schema_errors'])}", flush=True)
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{model.replace(':', '_').replace('/', '_')}__investigation.json"
    path.write_text(json.dumps(inv, ensure_ascii=False, indent=2), encoding="utf-8")
    ollama.generate(model=model, prompt="", keep_alive=0)


if __name__ == "__main__":
    args = sys.argv[1:]
    only_investigation = "--investigate-only" in args
    for m in (a for a in args if not a.startswith("--")):
        (evaluate_investigation_only if only_investigation else evaluate)(m)
