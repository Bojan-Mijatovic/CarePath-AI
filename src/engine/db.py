"""DuckDB layout of a run: one file per run, with the tables from spec/SPEC.md §3, §5.1 and §7.

A run is scenario × arm × levers (SPEC C2), stored as runs/<run_id>.duckdb. `scenario_truth`
is never in a run database (SPEC §3.3); it lives in demo/truth/. Of the views of SPEC §5.2, kpi_daily,
map_comuni and worklist_today are tables filled once per tick (steps 1.22, 2.2 and 2.4), and sankey_flows
is a DuckDB view over pathway_state (step 2.2).

    uv run carepath-db s2_agents [--overwrite]
"""

import argparse
import errno
import re
from pathlib import Path

import duckdb

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"
RUN_ID = re.compile(r"^s[1-3]_(agents|baseline)(_[A-Za-z0-9+\-]+)?$")

EVENT_TYPES = ("DISCHARGE", "ADMISSION", "VISIT", "IMAGING", "LAB", "DISPENSE", "TELEMON_START",
               "TELEMON_READING", "BOOKING", "CALL", "REMINDER")
PATHWAY_STATUSES = ("on_track", "due_soon", "overdue", "dropped")
KPI_LEVELS = ("ats", "asst", "comune")
ACTION_TYPES = ("reminder", "call_task", "notify_mmg", "reschedule", "enroll_proposal", "rule_proposal",
                "pathway_proposal", "bed_proposal", "bed_assignment")
ACTION_STATUSES = ("proposed", "approved", "executed", "rejected", "undone")
AUDIT_EVENTS = ("created", "approved", "rejected", "executed", "undone", "config_changed")


def _one_of(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


# No keys or indexes on events: it takes thousands of rows per tick and AC2 allows 1 s per day.
TABLES = {
    "events": f"""
        event_id      VARCHAR NOT NULL,
        patient_id    VARCHAR NOT NULL,
        day           INTEGER NOT NULL,
        event_type    VARCHAR NOT NULL CHECK (event_type IN {_one_of(EVENT_TYPES)}),
        code          VARCHAR,
        value         DOUBLE,
        facility_id   VARCHAR,
        asst_id       VARCHAR,
        mmg_id        VARCHAR NOT NULL,
        comune_istat  VARCHAR NOT NULL,
        source        VARCHAR NOT NULL CHECK (source IN ('sim', 'agent_action')),
        action_id     VARCHAR""",
    "patients": """
        patient_id       VARCHAR PRIMARY KEY,
        sex              VARCHAR NOT NULL CHECK (sex IN ('F', 'M')),
        age              INTEGER NOT NULL,
        comune_istat     VARCHAR NOT NULL,
        asst_id          VARCHAR NOT NULL,
        mmg_id           VARCHAR NOT NULL,
        lives_alone      BOOLEAN NOT NULL,
        ref_facility_id  VARCHAR NOT NULL,
        distance_km      DOUBLE NOT NULL,
        conditions       VARCHAR[] NOT NULL""",
    "comuni": """
        comune_istat       VARCHAR PRIMARY KEY,
        name               VARCHAR NOT NULL,
        asst_id            VARCHAR NOT NULL,
        population         INTEGER NOT NULL,
        population_65plus  INTEGER NOT NULL,
        lat                DOUBLE NOT NULL,
        lon                DOUBLE NOT NULL""",
    "mmg": """
        mmg_id        VARCHAR PRIMARY KEY,
        coop_id       VARCHAR NOT NULL,
        cs_id         VARCHAR NOT NULL,
        comune_istat  VARCHAR NOT NULL""",
    "facilities": """
        facility_id   VARCHAR PRIMARY KEY,
        name          VARCHAR NOT NULL,
        type          VARCHAR NOT NULL CHECK (type IN ('hospital', 'clinic')),
        asst_id       VARCHAR NOT NULL,
        comune_istat  VARCHAR NOT NULL,
        lat           DOUBLE NOT NULL,
        lon           DOUBLE NOT NULL""",
    "capacity_slots": """
        facility_id   VARCHAR NOT NULL,
        service       VARCHAR NOT NULL,
        day           INTEGER NOT NULL,
        slots_total   INTEGER NOT NULL,
        slots_booked  INTEGER NOT NULL,
        PRIMARY KEY (facility_id, service, day)""",
    "beds": """
        facility_id  VARCHAR NOT NULL,
        ward         VARCHAR NOT NULL,
        beds_total   INTEGER NOT NULL,
        PRIMARY KEY (facility_id, ward)""",
    "bed_occupancy": """
        day                          INTEGER NOT NULL,
        facility_id                  VARCHAR NOT NULL,
        ward                         VARCHAR NOT NULL,
        occupied                     INTEGER NOT NULL,
        expected_discharges_next_2d  INTEGER NOT NULL,
        PRIMARY KEY (day, facility_id, ward)""",
    "pathway_state": f"""
        patient_id       VARCHAR NOT NULL,
        pathway_id       VARCHAR NOT NULL,
        enrolled_day     INTEGER NOT NULL,
        enrolled_by      VARCHAR NOT NULL CHECK (enrolled_by IN ('mmg', 'agent')),
        current_step     VARCHAR,
        next_step        VARCHAR,
        next_due_day     INTEGER,
        next_booked_day  INTEGER,
        status           VARCHAR NOT NULL CHECK (status IN {_one_of(PATHWAY_STATUSES)}),
        overdue_steps    VARCHAR[] NOT NULL,
        escalation_step  INTEGER NOT NULL CHECK (escalation_step BETWEEN 0 AND 4),
        last_event_day   INTEGER,
        risk_score       DOUBLE NOT NULL,
        risk_drivers     VARCHAR[] NOT NULL,
        flags            VARCHAR[] NOT NULL,
        updated_day      INTEGER NOT NULL,
        PRIMARY KEY (patient_id, pathway_id)""",
    "kpi_daily": f"""
        day                       INTEGER NOT NULL,
        pathway_id                VARCHAR NOT NULL,
        level                     VARCHAR NOT NULL CHECK (level IN {_one_of(KPI_LEVELS)}),
        key                       VARCHAR NOT NULL,
        patients                  INTEGER NOT NULL,
        on_track_pct              DOUBLE NOT NULL,
        overdue                   INTEGER NOT NULL,
        dropped                   INTEGER NOT NULL,
        readmissions_30d          INTEGER NOT NULL,
        readmission_rate_30d      DOUBLE,
        actions_executed          INTEGER NOT NULL,
        actions_pending           INTEGER NOT NULL,
        est_readmission_cost_eur  INTEGER,
        PRIMARY KEY (day, pathway_id, level, key)""",
    "map_comuni": """
        comune_istat          VARCHAR NOT NULL,
        pathway_id            VARCHAR NOT NULL,
        adherence_pct         DOUBLE,
        risk_mean             DOUBLE,
        high_risk_patients    INTEGER,
        readmission_rate_30d  DOUBLE,
        alarm                 BOOLEAN NOT NULL,
        PRIMARY KEY (comune_istat, pathway_id)""",
    "worklist_today": """
        day              INTEGER NOT NULL,
        rank             INTEGER NOT NULL,
        patient_id       VARCHAR NOT NULL,
        risk_score       DOUBLE NOT NULL,
        reasons          JSON NOT NULL,
        pathways         VARCHAR[] NOT NULL,
        escalation_step  INTEGER NOT NULL,
        script           JSON,
        outcome          VARCHAR,
        PRIMARY KEY (day, patient_id)""",
    "actions": f"""
        action_id       VARCHAR PRIMARY KEY,
        agent           VARCHAR NOT NULL,
        type            VARCHAR NOT NULL CHECK (type IN {_one_of(ACTION_TYPES)}),
        patient_id      VARCHAR,
        scope           JSON,
        pathway_id      VARCHAR,
        payload         JSON NOT NULL,
        rationale       JSON NOT NULL,
        evidence        JSON NOT NULL,
        autonomy_level  INTEGER NOT NULL CHECK (autonomy_level BETWEEN 0 AND 3),
        status          VARCHAR NOT NULL CHECK (status IN {_one_of(ACTION_STATUSES)}),
        created_day     INTEGER NOT NULL,
        executed_day    INTEGER,
        decided_by      VARCHAR""",
    "audit_log": f"""
        ts_day     INTEGER NOT NULL,
        action_id  VARCHAR,
        event      VARCHAR NOT NULL CHECK (event IN {_one_of(AUDIT_EVENTS)}),
        actor      VARCHAR NOT NULL,
        details    JSON NOT NULL""",
}


VIEWS = {
    "sankey_flows": """
        SELECT pathway_id, current_step AS from_step, next_step AS to_step, status, count(*)::INTEGER AS patients
        FROM pathway_state GROUP BY ALL""",
}


def run_path(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    if not RUN_ID.match(run_id):
        raise ValueError(f"run_id {run_id!r} does not match s<scenario>_<arm>[_<lever-hash>] (SPEC §9)")
    return runs_dir / f"{run_id}.duckdb"


def create_tables(con: duckdb.DuckDBPyConnection) -> None:
    for name, columns in TABLES.items():
        con.execute(f"CREATE TABLE {name} ({columns})")
    for name, sql in VIEWS.items():
        con.execute(f"CREATE VIEW {name} AS {sql}")


def create_run(run_id: str, runs_dir: Path = RUNS_DIR, overwrite: bool = False) -> Path:
    """Create runs/<run_id>.duckdb with every table empty. Refuses to replace a run unless told to."""
    path = run_path(run_id, runs_dir)
    if path.exists():
        if not overwrite:
            raise FileExistsError(errno.EEXIST, "run exists; pass overwrite=True to replace it", str(path))
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(path) as con:
        create_tables(con)
    return path


def open_run(run_id: str, runs_dir: Path = RUNS_DIR) -> duckdb.DuckDBPyConnection:
    """The one connection the simulation process keeps to a run while it advances (SPEC §6, C12, D29):
    writable for the simulator, the state engine and the action service, but with access to every other
    file disabled and the configuration locked, so neither it nor a cursor of it can read demo/truth/."""
    con = duckdb.connect(run_path(run_id, runs_dir), config={"enable_external_access": False})
    con.execute("SET lock_configuration = true")
    return con


def tool_cursor(con: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    """What tools get in the simulation process: a cursor of the run's open_run connection. It can write,
    so the tools' own SELECT-only guard (agents.tools.Query) is what keeps them read-only (D29)."""
    return con.cursor()


def connect_for_tools(run_id: str, runs_dir: Path = RUNS_DIR) -> duckdb.DuckDBPyConnection:
    """The only connection agent tools get (SPEC §6, step 1.18): read-only, no access to any file outside
    the run database (so not demo/truth/ either), and the configuration locked so a tool cannot undo it."""
    con = duckdb.connect(run_path(run_id, runs_dir), read_only=True, config={"enable_external_access": False})
    con.execute("SET lock_configuration = true")
    return con


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an empty run database (delivery plan, step 0.9).")
    parser.add_argument("run_id", help="for example s2_agents")
    parser.add_argument("--overwrite", action="store_true", help="replace an existing run")
    args = parser.parse_args()
    try:
        print(create_run(args.run_id, overwrite=args.overwrite))
    except FileExistsError as e:
        parser.error(f"{e.filename} exists; add --overwrite to replace it")
    except ValueError as e:
        parser.error(str(e))


if __name__ == "__main__":
    main()
