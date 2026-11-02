"""AC10: Verifier catches all injected wrong numbers in 5 answers, no false alarms.

Measured by: injected errors. Owner: R3. Layer: optional. Spec: SPEC.md §6 (C33), §11.
The 5 answers are the ones Chiedi shows in the demo: each scenario's echo investigation and scenario 2's two
questions (demo/cache/manifest.json), replayed from the cache on the alarm's day (the `alarm_investigations`
fixture), each step with its tool's result of that day.

No false alarms: in the answers as the model wrote them, the Verifier flags exactly the slips in SLIPS, each
read by hand. Injected errors: every number of every claim, changed in the Italian or in the English text
alone, gives the claim one more number issue.
"""

import re

import pytest

from agents import verifier
from engine import pathway as pathway_model

HF = pathway_model.load("hf_lombardia_v1")

# (scenario, answer) -> {claim index: issue kinds}, the answer being "echo" or the question's index. Read by
# hand on 2 Nov 2026 against the tool results:
SLIPS = {
    # s1 [2] ASST Mantova's overdue patients as Ospedale A's; [3] ASST Mantova's compliance as Ospedale A's (the
    # translation's "81.-82%" passes: 81 and 82 are both 81,82% rounded)
    (1, "echo"): {2: ["scope"], 3: ["scope"]},
    # s2 [2] ASST Cremona's patients as Ospedale B's, the translation wrote "4-than" for 40 giorni; [3] "83,65%
    # … inferiore al 79,8%" and ASST Cremona's compliance as Ospedale B's
    (2, "echo"): {2: ["number", "scope"], 3: ["comparison", "scope"]},
    # s3 [2] ASST Crema's patients as Ospedale C's; [3] "83,05% … inferiore al 77,52%", ASST Crema's compliance
    (3, "echo"): {2: ["scope"], 3: ["comparison", "scope"]},
    (2, 0): {},
    (2, 1): {},
}


@pytest.fixture(scope="module")
def answers(alarm_investigations):
    """{(scenario, answer): (stored investigation, facilities)} for the 5 answers."""
    out = {}
    for n, (invs, names, assts, asked) in alarm_investigations.items():
        facilities = [(name, "hospital" if name.startswith("Ospedale") else "clinic", assts[f]) for f, name in names.items()]
        echo = [i for i in invs if i and any(s["tool"] == "wait_by_hospital" and s["step"] == 1 for s in i["steps"])]
        assert len(echo) == 1, [i and i["question"]["it"] for i in invs]
        out[(n, "echo")] = (echo[0], facilities)
        out |= {(n, k): (a, facilities) for k, a in enumerate(asked)}
    assert sorted(out, key=str) == sorted(SLIPS, key=str)
    return out


def _verdicts(inv: dict, facilities: list, claims: list[dict] | None = None):
    results = {s["step"]: s["result"] for s in inv["steps"]}
    return verifier.verdicts(claims or inv["claims"], results, inv["question"], HF, facilities)


def _changed(token: str) -> str:
    """A wrong number written as the token is: a quarter more and one unit of the last digit, 0 becomes 3."""
    sep = next((c for c in token if c in ",."), None)
    decimals = len(token.split(sep)[-1]) if sep else 0
    x = float(token.replace(",", ".").lstrip("-−"))
    new = round(x * 1.25 + 10 ** -decimals, decimals) if x else 3
    return f"{new:.{decimals}f}".replace(".", sep) if sep else str(int(new))


@pytest.mark.acceptance
@pytest.mark.parametrize("key", list(SLIPS), ids=str)
def test_ac10_no_false_alarms(answers, key):
    inv, facilities = answers[key]
    got = {i: [issue["kind"] for issue in issues] for i, (_, issues) in enumerate(_verdicts(inv, facilities)) if issues}
    assert got == SLIPS[key], [(i, c["text"]["it"], issues) for i, (c, (_, issues))
                               in enumerate(zip(inv["claims"], _verdicts(inv, facilities))) if issues]
    # the tick verified the stored claims the same way, on the same day
    assert [c["verified"] for c in inv["claims"]] == [v for v, _ in _verdicts(inv, facilities)]


@pytest.mark.acceptance
@pytest.mark.parametrize("key", list(SLIPS), ids=str)
def test_ac10_injected_numbers_caught(answers, key):
    inv, facilities = answers[key]
    words = "|".join(sorted({re.escape(n.split()[0][:-1]) for n, _, _ in facilities}))
    injected, missed = 0, []
    for claim in inv["claims"]:
        step = next(s for s in inv["steps"] if s["step"] == claim["step"])
        named = list(verifier.labels(step["result"]["data"], HF))
        for lang in ("it", "en"):
            tokens, _ = verifier._numbers(claim["text"][lang], named, words)
            for t in tokens:
                text, new = claim["text"][lang], _changed(t.group())
                wrong = {**claim, "text": {**claim["text"], lang: text[:t.start()] + new + text[t.end():]}}
                (_, issues), = _verdicts(inv, facilities, [wrong])
                injected += 1
                spelled = "|".join(re.escape(new.replace(*s)) for s in ((",", "."), (".", ",")))  # "2.1" in Italian
                if not any(i["kind"] == "number" and re.match(rf"(?:{spelled})%?:", i["text"][lang]) for i in issues):
                    missed.append((lang, t.group(), new, text))
    assert not missed, missed
    assert injected >= 5  # every answer has numbers to change
