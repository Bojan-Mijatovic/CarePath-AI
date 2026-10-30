"""Action service (SPEC §7.3): the only writer of `actions` and `audit_log`.

An agent hands it an action; it checks the guardrails and the evidence (a failure rejects the action), then
the autonomy level of the type and the daily limit per facility (either sends it to the approval queue),
and executes the rest at once. Executing writes the audit log and hands the action to `emit`, which the
engine gives: it turns the action into simulation events through the feedback hook (SPEC §9), since agent
code never touches the simulator (CLAUDE.md rule 5). The manager's decisions (step 2.18) and undo go
through the same functions. Every function returns the action rows it changed, for the `action` messages.

The checks that reject come before the ones that queue: an action that may never run does not wait for a
decision. The compensating event of an undo is type-specific and comes with the effects of step 2.13.
"""

import json

import duckdb

# SPEC §7.2: the default level per type, and the types whose level is fixed. bed_proposal is not in the
# table, so it has no level of its own.
DEFAULT_LEVELS = {"reminder": 3, "call_task": 3, "notify_mmg": 2, "reschedule": 2, "enroll_proposal": 3,
                  "pathway_proposal": 3, "rule_proposal": 1, "bed_assignment": 3}
FIXED = {"rule_proposal"}  # the manager always approves a rule
MANAGER = "manager"  # the demo has no login; the prototype's "Menadžment"
SERVICE = "action_service"
DAILY_LIMIT = 50  # automatic actions per facility and day (SPEC §7.3)
# Guardrails that cannot be switched off (SPEC §7.3, CLAUDE.md rule 2): no field of an action may carry a
# therapy or a diagnosis, and a reschedule moves an existing booking, it never books a new exam.
CLINICAL_FIELDS = {"therapy", "drug", "dose", "atc", "prescription", "diagnosis", "icd", "icd10"}
JSON_FIELDS = ("scope", "payload", "rationale", "evidence")


def levels(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """The level in force per type: the defaults, then every `config_changed` in the audit log in order."""
    out = dict(DEFAULT_LEVELS)
    for (details,) in con.execute("""SELECT details FROM audit_log WHERE event = 'config_changed'
                                     ORDER BY ts_day, rowid""").fetchall():
        d = json.loads(details)
        if d.get("setting") == "autonomy":
            out[d["type"]] = d["level"]
    return out


def settings(con: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    """GET /api/settings (C30): per type the level in force, its default, and whether it is fixed."""
    now = levels(con)
    return {t: {"level": now[t], "default": d, "fixed": t in FIXED} for t, d in DEFAULT_LEVELS.items()}


def set_level(con: duckdb.DuckDBPyConnection, day: int, action_type: str, level: int, actor: str = MANAGER) -> None:
    """The manager's change of one type's level; ValueError for an unknown type, a level outside 0–3 or a
    fixed type."""
    if action_type not in DEFAULT_LEVELS:
        raise ValueError(f"action type is one of {sorted(DEFAULT_LEVELS)}")
    if not 0 <= level <= 3:
        raise ValueError("level is between 0 and 3")
    if action_type in FIXED and level != DEFAULT_LEVELS[action_type]:
        raise ValueError(f"{action_type} stays at level {DEFAULT_LEVELS[action_type]}")
    before = levels(con)[action_type]
    _audit(con, day, None, "config_changed", actor,
           {"setting": "autonomy", "type": action_type, "level": level, "before": before})


def create(con: duckdb.DuckDBPyConnection, run_id: str, day: int, action: dict, emit) -> dict:
    """An agent's action ({agent, type, patient_id, scope, pathway_id, payload, rationale, evidence}) through
    the checks of SPEC §7.3, in the order above. Returns the stored row: `rejected`, `proposed` or `executed`."""
    n = con.execute("SELECT count(*) FROM actions").fetchall()[0][0]
    level = levels(con).get(action["type"])
    row = {"action_id": f"act_{run_id}_{n + 1}", "agent": action["agent"], "type": action["type"],
           "patient_id": action.get("patient_id"), "scope": action.get("scope"), "pathway_id": action.get("pathway_id"),
           "payload": action.get("payload") or {}, "rationale": action["rationale"], "evidence": action.get("evidence") or [],
           "autonomy_level": 0 if level is None else level, "status": "proposed", "created_day": day,
           "executed_day": None, "decided_by": None}
    reason = _guardrail(row) or (None if row["evidence"] else "no tool source as evidence")
    queued = None
    if reason:
        row.update(status="rejected", decided_by=SERVICE)
    elif level < 3:
        queued = f"autonomy level {level}"
    elif _automatic_today(con, day, _facility(row)) >= DAILY_LIMIT:
        queued = f"daily limit of {DAILY_LIMIT} automatic actions reached"
    _insert(con, row)
    _audit(con, day, row["action_id"], "created", row["agent"], {"queued": queued} if queued else {})
    if reason:
        _audit(con, day, row["action_id"], "rejected", SERVICE, {"reason": reason})
    elif not queued:
        _execute(con, day, row, "auto", emit)
    return row


def decide(con: duckdb.DuckDBPyConnection, day: int, action_id: str, approve: bool, emit,
           actor: str = MANAGER) -> dict:
    """Approve or reject an action waiting in the queue; an approved action is executed at once. KeyError if
    there is no such action, ValueError if it is not waiting."""
    row = _row(con, action_id)
    if row["status"] != "proposed":
        raise ValueError(f"action {action_id} is {row['status']}, not waiting for a decision")
    if not approve:
        row.update(status="rejected", decided_by=actor)
        con.execute("UPDATE actions SET status = 'rejected', decided_by = $a WHERE action_id = $id",
                    {"a": actor, "id": action_id})
        _audit(con, day, action_id, "rejected", actor, {})
        return row
    _audit(con, day, action_id, "approved", actor, {})
    _execute(con, day, row, actor, emit)
    return row


def undo(con: duckdb.DuckDBPyConnection, day: int, action_id: str, actor: str = MANAGER) -> dict:
    """Undo an executed action: status `undone` and an `undone` entry. KeyError if there is no such action,
    ValueError if it was not executed."""
    row = _row(con, action_id)
    if row["status"] != "executed":
        raise ValueError(f"action {action_id} is {row['status']}; only an executed action can be undone")
    row["status"] = "undone"
    con.execute("UPDATE actions SET status = 'undone' WHERE action_id = $id", {"id": action_id})
    _audit(con, day, action_id, "undone", actor, {})
    return row


def _guardrail(row: dict) -> str | None:
    if row["type"] not in DEFAULT_LEVELS:
        return f"no autonomy level for {row['type']}"
    fields = set(row["payload"]) | set(row["scope"] or {})
    if fields & CLINICAL_FIELDS:
        return f"clinical fields {sorted(fields & CLINICAL_FIELDS)}: no therapy and no diagnosis"
    if row["type"] == "reschedule" and "from_facility" not in row["payload"]:
        return "a reschedule moves an existing booking and names where it was"
    return None


def _facility(row: dict) -> str | None:
    return (row["scope"] or {}).get("facility_id") or row["payload"].get("from_facility") or row["payload"].get("facility_id")


def _automatic_today(con: duckdb.DuckDBPyConnection, day: int, facility: str | None) -> int:
    """Actions executed without a person today for the facility; an action without a facility has no limit."""
    if facility is None:
        return 0
    return con.execute("""
        SELECT count(*) FROM actions WHERE decided_by = 'auto' AND executed_day = $d
          AND coalesce(json_extract_string(scope, '$.facility_id'), json_extract_string(payload, '$.from_facility'),
                       json_extract_string(payload, '$.facility_id')) = $f""", {"d": day, "f": facility}).fetchall()[0][0]


def _execute(con: duckdb.DuckDBPyConnection, day: int, row: dict, decided_by: str, emit) -> None:
    row.update(status="executed", executed_day=day, decided_by=decided_by)
    con.execute("UPDATE actions SET status = 'executed', executed_day = $d, decided_by = $a WHERE action_id = $id",
                {"d": day, "a": decided_by, "id": row["action_id"]})
    _audit(con, day, row["action_id"], "executed", "auto" if decided_by == "auto" else SERVICE, {})
    emit([row])


def _insert(con: duckdb.DuckDBPyConnection, row: dict) -> None:
    values = {k: json.dumps(v, ensure_ascii=False) if k in JSON_FIELDS and v is not None else v for k, v in row.items()}
    con.execute(f"INSERT INTO actions BY NAME SELECT {', '.join(f'${k} AS {k}' for k in values)}", values)


def _row(con: duckdb.DuckDBPyConnection, action_id: str) -> dict:
    cur = con.execute("SELECT * FROM actions WHERE action_id = $id", {"id": action_id})
    found = cur.fetchall()
    if not found:
        raise KeyError(action_id)
    row = dict(zip([d[0] for d in cur.description], found[0]))
    return {k: json.loads(v) if k in JSON_FIELDS and v is not None else v for k, v in row.items()}


def _audit(con: duckdb.DuckDBPyConnection, day: int, action_id: str | None, event: str, actor: str,
           details: dict) -> None:
    con.execute("INSERT INTO audit_log VALUES ($d, $id, $e, $a, $j)",
                {"d": day, "id": action_id, "e": event, "a": actor, "j": json.dumps(details)})
