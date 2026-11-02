"""Verifier: checks every claim of an investigation against the tool call it points at (SPEC §6, C33;
delivery plan Phase 3, AC10).

Code only, no model (Solution Plan §7: the LLM's part is "minimal or none"). For each claim it repeats the
step's call, tool and arguments as stored (C5), on the same day, so the result has the bytes the
Investigator saw (C7). Then it checks the claim's text, Italian and English:

- numbers: each one is in the tool's data, where a fraction may be written as a percentage, in the call's
  arguments, or in the question (the alarm's own numbers). A number written next to a name of the data (a
  hospital, a comune, a patient, a step) must be that name's value. It may be rounded or cut to the
  decimals the text shows, no further. The Investigator's prompt says every number comes from a tool, so a
  threshold the model made up ("soglia regionale di 95%") is an issue too.
- comparisons (Italian): "inferiore", "superiore" and their kin between two numbers of the same unit hold.
  Step 2.9 found "83,65% … inferiore al 79,8%".
- scope (Italian): a facility the claim names, on a tool that does not answer per facility, gets the
  scope the figure is for ("La compliance all'Ospedale B" over ASST Cremona's data, step 2.9).

A claim passes (`verified` true) or keeps its text with `issues`, each a correction filled by code from
the tool's data in both languages. A step whose call no longer returns data leaves its claims unverified
(null), and the console shows them without a badge (Solution Plan §7).
"""

import re

from agents import tools
from agents.investigator import Investigation
from engine.pathway import Pathway

NUMBER = re.compile(r"(?<![\w.,])[-−]?\d+(?:[.,]\d+)*(?!\w)")
REST = re.compile(r"\b(?:rest[oi]\s+(?:dell['’]\s*|di\s+)?|rest\s+of\s+(?:the\s+)?)ATS\b", re.IGNORECASE)
LESS = re.compile(r"\b(?:inferior[ei]|minor[ei]|più\s+bass[aeio]|(?:al\s+di\s+)?sotto)\b", re.IGNORECASE)
MORE = re.compile(r"\b(?:superior[ei]|maggior[ei]|più\s+alt[aeio]|sopra|super(?:a|ano|ando))\b", re.IGNORECASE)
SENTENCE = re.compile(r"[.;:](?:\s|$)")
BEFORE_GAP, AFTER_GAP, COMPARE_GAP = 40, 20, 40  # characters between a name or a comparison and its number
LIST_TAIL = r"(?:\s*(?:,|\be\b|\bed\b|\band\b)\s*[A-Z0-9]{1,2}\b)+"  # "Poliambulatorio 1, 2, 3 e 6"


def readings(token: str) -> list[tuple[float, int]]:
    """The (value, decimals) a number can mean in Italian or English text: "87,31" is 87.31; "2.400" is
    2400 in Italian and 2.4 in English."""
    sign, t = (-1, token[1:]) if token[0] in "-−" else (1, token)
    out = []
    for dec, thousands in ((",", "."), (".", ",")):
        parts = t.split(dec)
        groups = parts[0].split(thousands)
        if len(parts) > 2 or (len(parts) == 2 and thousands in parts[1]) or any(len(g) != 3 for g in groups[1:]):
            continue
        out.append((sign * float("".join(groups) + ("." + parts[1] if len(parts) == 2 else "")),
                    len(parts[1]) if len(parts) == 2 else 0))
    return list(dict.fromkeys(out))


def matches(x: float, decimals: int, value: float) -> bool:
    """`x` as written is `value`, or the value as a percentage, rounded or cut to the text's decimals; the
    sign is free ("una differenza di -11,83 punti", "inferiore di 11,83 punti")."""
    unit = 10 ** -decimals
    return any(abs(abs(x) - abs(v)) < unit - 1e-9 for v in (value, value * 100))


def leaves(obj) -> list[float]:
    """Every number in a tool's data or arguments."""
    if isinstance(obj, bool) or obj is None:
        return []
    if isinstance(obj, (int, float)):
        return [float(obj)]
    if isinstance(obj, dict):
        return [x for v in obj.values() for x in leaves(v)]
    if isinstance(obj, list):
        return [x for v in obj for x in leaves(v)]
    return []


def labels(data, pathway: Pathway) -> dict[str, list[float]]:
    """Names in the data, each with the numbers it owns: the keys of a {name: number} mapping (a hospital,
    a comune, a step, also by its label), and the strings of a record in a list (a patient id, an area's
    comuni) with the record's numbers. "rest_of_ats" is found by its words (REST)."""
    out: dict[str, list[float]] = {}
    step_labels = {s.id: [s.label.it, s.label.en] for s in pathway.steps}
    # a name has a capital or a digit ("Ospedale B", "Camisano", "coop_6"); "count", "patients" are fields
    is_name = lambda k: k in step_labels or k == "rest_of_ats" or k != k.lower() or any(ch.isdigit() for ch in k)

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool) and is_name(k):
                    for name in [k, *step_labels.get(k, [])]:
                        out.setdefault(name, []).append(float(v))
                elif isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    owned = leaves(item)
                    for v in item.values():
                        for name in v if isinstance(v, list) else [v]:
                            if isinstance(name, str):
                                out.setdefault(name, []).extend(owned)
                walk(item)

    walk(data)
    return {k: v for k, v in out.items() if len(k) >= 3}  # "a" and "b" of compare_segments are words too


def _places(text: str, names: list[str]) -> list[tuple[int, int, str]]:
    """(start, end, name) of each name in the text, the longest first where two overlap."""
    found, taken = [], set()
    for name in sorted(names, key=len, reverse=True):
        pattern = REST if name == "rest_of_ats" else re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", re.IGNORECASE)
        for m in pattern.finditer(text):
            if not taken & set(range(m.start(), m.end())):
                found.append((m.start(), m.end(), name))
                taken |= set(range(m.start(), m.end()))
    return sorted(found)


def _mask(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in spans:
        text = text[:start] + "\0" * (end - start) + text[end:]
    return text


def _numbers(text: str, names: list[str], facility_words: str) -> tuple[list[re.Match], list[tuple[int, int, str]]]:
    """The number tokens of a text and the names around them. Digits inside a name ("Poliambulatorio 5",
    "coop_6", "p_00366") and a list of facility letters or numbers after a facility word are not numbers."""
    places = _places(text, names)
    masked = text
    if facility_words:
        tails = re.finditer(rf"\b(?:{facility_words})\w*\s+[A-Z0-9]{{1,2}}\b(?:{LIST_TAIL})?", text)
        masked = _mask(masked, [m.span() for m in tails])
    masked = _mask(masked, [(s, e) for s, e, _ in places])
    return list(NUMBER.finditer(masked)), places


def _bound(token: re.Match, tokens: list[re.Match], places: list[tuple[int, int, str]], text: str) -> list[str]:
    """The names a number may belong to: the nearest before it and one just after it ("83,65% per
    l'ecocardiogramma"; "76,47% per la visita, 81,82% per l'eco" puts a name on both sides), each with no
    other number and no sentence end between."""
    def clear(a: int, b: int, gap: int, comma_ok: bool) -> bool:
        between = text[a:b]
        return (b - a <= gap and not any(a <= t.start() < b for t in tokens) and not SENTENCE.search(between)
                and (comma_ok or "," not in between))
    after_of = lambda t: [p for p in places if p[0] >= t.end() and clear(t.end(), p[0], AFTER_GAP, False)][:1]
    taken = {p for t in tokens if t is not token for p in after_of(t)}  # a name already after an earlier number
    before = [p[2] for p in places if p[1] <= token.start() and p not in taken
              and clear(p[1], token.start(), BEFORE_GAP, True)]
    return before[-1:] + [p[2] for p in after_of(token)]


def _format(x: float, decimals: int, lang: str, percent: bool) -> str:
    text = f"{x:.{decimals}f}" + ("%" if percent else "")
    return text.replace(".", ",") if lang == "it" else text


def _unit(text: str, token: re.Match) -> str:
    """What a number counts: "%" or the word after it ("giorni", "pazienti", "punti")."""
    m = re.match(r"\s*(%|[^\W\d]+)", text[token.end():])
    return m.group(1).lower() if m else ""


def _who(name: str, lang: str) -> str:
    return {"it": "resto dell'ATS", "en": "rest of the ATS"}[lang] if name == "rest_of_ats" else name


def number_issues(text: str, lang: str, tool: str, named: dict[str, list[float]], data: list[float],
                  call: list[float], facility_words: str) -> list[dict]:
    """Numbers of one text that are not the tool's. `data` are the numbers of the tool's data, `call` those
    of its arguments and the question: a number next to a name must be that name's value, or describe the
    call ("negli ultimi 7 giorni")."""
    tokens, places = _numbers(text, list(named), facility_words)
    issues = []
    for token in tokens:
        options = readings(token.group())
        names = _bound(token, tokens, places, text)
        values = [v for n in names for v in named[n]] + call if names else data + call
        if any(matches(x, d, v) for x, d in options for v in values):
            continue
        x, d = options[0] if lang == "it" else options[-1]
        percent = _unit(text, token) == "%"
        shown = {lng: _format(x, d, lng, percent) for lng in ("it", "en")}
        if names and names[0] in [p[2] for p in places if p[1] <= token.start()]:  # the name before it: its value
            v, scaled = min(((v, s) for v in named[names[0]] for s in (False, True)),
                            key=lambda vs, x=x: abs(abs(vs[0] * (100 if vs[1] else 1)) - abs(x)))
            right = {lng: _format(v * (100 if scaled else 1), d, lng, scaled) for lng in ("it", "en")}
            text_ = {"it": f"{shown['it']}: per {_who(names[0], 'it')} {tool} dà {right['it']}",
                     "en": f"{shown['en']}: {tool} gives {right['en']} for {_who(names[0], 'en')}"}
        else:
            text_ = {"it": f"{shown['it']}: non viene da {tool} né dalla domanda",
                     "en": f"{shown['en']}: not from {tool} or the question"}
        if lang == "en":  # the translation's own slip (D31): the Italian the model wrote has it right
            text_ = {"it": text_["it"] + " (testo inglese)", "en": text_["en"] + " (English text)"}
        issues.append({"kind": "number", "value": x, "text": text_})
    return issues


def comparison_issues(text: str, facility_words: str, names: list[str], call: list[float]) -> list[dict]:
    """A "less than" or "more than" between the nearest number before it and the first after it, of the
    same unit, in one sentence. A number of the call ("negli ultimi 7 giorni") is not compared, and
    "inferiore di 9,14 punti" states a difference, not a comparison."""
    tokens, _ = _numbers(text, names, facility_words)
    of_call = lambda t: any(matches(x, d, v) for x, d in readings(t.group()) for v in call)
    issues = []
    for pattern, holds, word in ((LESS, lambda a, b: a < b, ("inferiore", "lower")),
                                 (MORE, lambda a, b: a > b, ("superiore", "higher"))):
        for m in pattern.finditer(text):
            if re.match(r"\s+(?:di|by)\s+[-−]?\d", text[m.end():]):
                continue
            after = [t for t in tokens if t.start() >= m.end() and t.start() - m.end() <= COMPARE_GAP
                     and not SENTENCE.search(text[m.end():t.start()])]
            if not after:
                continue
            b = after[0]
            before = [t for t in tokens if t.end() <= m.start() and _unit(text, t) == _unit(text, b)
                      and not of_call(t) and not SENTENCE.search(text[t.end():m.start()])]
            if not before:
                continue
            a = before[-1]
            (x, d), (y, e) = readings(a.group())[0], readings(b.group())[0]
            if not holds(abs(x), abs(y)):
                percent = _unit(text, b) == "%"
                issues.append({"kind": "comparison", "value": x, "text": {
                    "it": f"{_format(x, d, 'it', percent)} non è {word[0]} a {_format(y, e, 'it', percent)}",
                    "en": f"{_format(x, d, 'en', percent)} is not {word[1]} than {_format(y, e, 'en', percent)}"}})
    return issues


def scope_issues(text: str, result: dict, named: dict[str, list[float]], facilities: list[tuple[str, str, str]]) -> list[dict]:
    """A facility the claim names, on a tool whose data is not per facility: the figure is the ASST's or
    the ATS's, from the call's arguments."""
    names = {name for name, _, _ in facilities}
    if names & set(named):
        return []  # the tool answers per facility; a name missing from it is a number's business
    args, tool = result["source"]["args"], result["source"]["tool"]
    asst = args.get("asst") or next((s.get("asst_id") for s in (args.get("a"), args.get("b")) if isinstance(s, dict)
                                     and s.get("asst_id")), None)
    scope = ({"it": f"ASST {asst.removeprefix('asst_').title()}", "en": f"ASST {asst.removeprefix('asst_').title()}"}
             if asst else {"it": "tutta l'ATS", "en": "the whole ATS"})
    return [{"kind": "scope", "value": None, "text": {
                "it": f"{tool} dà il dato di {scope['it']}, non di {name}",
                "en": f"{tool} gives the figure for {scope['en']}, not for {name}"}}
            for _, _, name in _places(text, sorted(names))]


def _string_numbers(obj) -> list[float]:
    """Numbers inside the data's names, as a claim may spell them out: a driver "weight_gain_3d" is "aumento
    di peso in 3 giorni"."""
    if isinstance(obj, str):
        return [float(n) for n in re.findall(r"\d+", obj)]
    if isinstance(obj, dict):
        return [x for k, v in obj.items() for x in _string_numbers(k) + _string_numbers(v)]
    if isinstance(obj, list):
        return [x for v in obj for x in _string_numbers(v)]
    return []


def unsupported(text: str, values: list[float]) -> list[str]:
    """The numbers of a text that are none of `values`, rounded or cut as `matches` allows: the check of a
    model's sentence around numbers code gave it (Intervention's capacity proposal, step 2.27)."""
    return [t.group() for t in NUMBER.finditer(text)
            if not any(matches(x, d, v) for x, d in readings(t.group()) for v in values)]


def check(text: dict, result: dict, question: dict, pathway: Pathway,
          facilities: list[tuple[str, str, str]]) -> list[dict]:
    """The issues of one claim ({"it", "en"}) against its tool's result; none means verified."""
    data, tool = result["data"], result["source"]["tool"]
    named = labels(data, pathway)
    call = leaves(result["source"]["args"]) + [
        x for lang in ("it", "en") for t in NUMBER.finditer(question[lang]) for x, _ in readings(t.group())]
    values = leaves(data) + _string_numbers(data)
    words = "|".join(sorted({re.escape(n.split()[0][:-1]) for n, _, _ in facilities if " " in n}))
    issues = [*number_issues(text["it"], "it", tool, named, values, call, words),
              *number_issues(text["en"], "en", tool, named, values, call, words),
              *comparison_issues(text["it"], words, list(named), call),
              *scope_issues(text["it"], result, named, facilities)]
    seen, out = set(), []
    for issue in issues:  # the same wrong number in both languages is one issue, the Italian one
        key = (issue["kind"], issue["value"], None if issue["value"] is not None else issue["text"]["it"])
        if key not in seen:
            seen.add(key)
            out.append({"kind": issue["kind"], "text": issue["text"]})
    return out


def verify(ctx: tools.Context, pathway: Pathway, inv: Investigation, facilities: list[tuple[str, str, str]]) -> Investigation:
    """Sets `verified` and `issues` on each claim of `inv`, from its step's call repeated on `ctx` (the run on
    the investigation's day). `facilities` are (name, type, asst_id), as the Investigator got them."""
    results = {s["step"]: tools.call(ctx, s["tool"], s["args"]) for s in inv.steps
               if any(c["step"] == s["step"] for c in inv.claims)}
    for claim, (verified, issues) in zip(inv.claims, verdicts(inv.claims, results, inv.question, pathway, facilities)):
        claim["verified"], claim["issues"] = verified, issues
    return inv


def verdicts(claims: list[dict], results: dict[int, dict], question: dict, pathway: Pathway,
             facilities: list[tuple[str, str, str]]) -> list[tuple[bool | None, list[dict]]]:
    """(verified, issues) per claim, from the repeated call of each step (`results`, by step number)."""
    out = []
    for claim in claims:
        result = results[claim["step"]]
        if "data" not in result:
            out.append((None, []))
            continue
        issues = check(claim["text"], result, question, pathway, facilities)
        out.append((not issues, issues))
    return out
