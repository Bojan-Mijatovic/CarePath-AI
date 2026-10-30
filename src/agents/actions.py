"""Action service (SPEC §7.3): the only writer of `actions` and `audit_log`.

Step 2.18 gives it the decisions the console makes: the autonomy level per action type (SPEC §7.2), changed
by the manager and logged as `config_changed`, and approve or reject of an action waiting in the queue.
Creating and executing actions, the guardrails, the daily limit and undo come with step 2.12.
"""

import json

import duckdb

# SPEC §7.2: the default level per type, and the types whose level is fixed. bed_proposal is not in the
# table, so it has no level of its own.
DEFAULT_LEVELS = {"reminder": 3, "call_task": 3, "notify_mmg": 2, "reschedule": 2, "enroll_proposal": 3,
                  "pathway_proposal": 3, "rule_proposal": 1, "bed_assignment": 3}
FIXED = {"rule_proposal"}  # the manager always approves a rule
MANAGER = "manager"  # the demo has no login; the prototype's "Menadžment"


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


def decide(con: duckdb.DuckDBPyConnection, day: int, action_id: str, approve: bool, actor: str = MANAGER) -> None:
    """Approve or reject an action waiting in the queue. KeyError if there is no such action, ValueError
    if it is not waiting. An approved action stays `approved` until the action service executes it."""
    found = con.execute("SELECT status FROM actions WHERE action_id = $id", {"id": action_id}).fetchall()
    if not found:
        raise KeyError(action_id)
    if found[0][0] != "proposed":
        raise ValueError(f"action {action_id} is {found[0][0]}, not waiting for a decision")
    status = "approved" if approve else "rejected"
    con.execute("UPDATE actions SET status = $s, decided_by = $a WHERE action_id = $id",
                {"s": status, "a": actor, "id": action_id})
    _audit(con, day, action_id, status, actor, {})


def _audit(con: duckdb.DuckDBPyConnection, day: int, action_id: str | None, event: str, actor: str,
           details: dict) -> None:
    con.execute("INSERT INTO audit_log VALUES ($d, $id, $e, $a, $j)",
                {"d": day, "id": action_id, "e": event, "a": actor, "j": json.dumps(details)})
