import duckdb
import pytest

from engine.db import create_run, run_path

# Column lists copied from spec/SPEC.md §3, §5.1 and §7, so a drift between code and contract fails here.
SPEC_COLUMNS = {
    "events": ["event_id", "patient_id", "day", "event_type", "code", "value", "facility_id", "asst_id",
               "mmg_id", "comune_istat", "source", "action_id"],
    "patients": ["patient_id", "sex", "age", "comune_istat", "asst_id", "mmg_id", "lives_alone",
                 "ref_facility_id", "distance_km", "conditions"],
    "comuni": ["comune_istat", "name", "asst_id", "population", "population_65plus", "lat", "lon"],
    "mmg": ["mmg_id", "coop_id", "cs_id", "comune_istat"],
    "facilities": ["facility_id", "name", "type", "asst_id", "comune_istat", "lat", "lon"],
    "capacity_slots": ["facility_id", "service", "day", "slots_total", "slots_booked"],
    "beds": ["facility_id", "ward", "beds_total"],
    "bed_occupancy": ["day", "facility_id", "ward", "occupied", "expected_discharges_next_2d"],
    "pathway_state": ["patient_id", "pathway_id", "enrolled_day", "enrolled_by", "current_step", "next_step",
                      "next_due_day", "next_booked_day", "status", "overdue_steps", "escalation_step",
                      "last_event_day", "risk_score", "risk_drivers", "flags", "updated_day"],
    "actions": ["action_id", "agent", "type", "patient_id", "scope", "pathway_id", "payload", "rationale",
                "evidence", "autonomy_level", "status", "created_day", "executed_day", "decided_by"],
    "audit_log": ["ts_day", "action_id", "event", "actor", "details"],
}


def columns(con, table):
    return [r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()]


def test_run_has_every_spec_table_and_column(tmp_path):
    path = create_run("s2_agents", runs_dir=tmp_path)
    assert path == tmp_path / "s2_agents.duckdb"
    with duckdb.connect(path, read_only=True) as con:
        tables = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
        assert tables == set(SPEC_COLUMNS)
        for table, expected in SPEC_COLUMNS.items():
            assert columns(con, table) == expected, table


def test_run_has_no_scenario_truth(tmp_path):
    with duckdb.connect(create_run("s1_baseline", runs_dir=tmp_path), read_only=True) as con:
        assert con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = 'scenario_truth'").fetchone() == (0,)


def test_existing_run_is_not_replaced_without_overwrite(tmp_path):
    path = create_run("s3_agents", runs_dir=tmp_path)
    with duckdb.connect(path) as con:
        con.execute("INSERT INTO mmg VALUES ('mmg_001', 'coop_1', 'cs_1', '020030')")
    with pytest.raises(FileExistsError):
        create_run("s3_agents", runs_dir=tmp_path)
    create_run("s3_agents", runs_dir=tmp_path, overwrite=True)
    with duckdb.connect(path, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM mmg").fetchone() == (0,)


@pytest.mark.parametrize("run_id", ["s2_agents", "s2_baseline", "s2_agents_echo+1"])
def test_spec_run_ids_are_accepted(run_id, tmp_path):
    assert run_path(run_id, tmp_path).name == f"{run_id}.duckdb"


@pytest.mark.parametrize("run_id", ["s4_agents", "s2_other", "../s2_agents", "s2_agents_a/b"])
def test_bad_run_ids_are_rejected(run_id, tmp_path):
    with pytest.raises(ValueError):
        run_path(run_id, tmp_path)


def test_allowed_codes_are_enforced(tmp_path):
    with duckdb.connect(create_run("s1_agents", runs_dir=tmp_path)) as con:
        con.execute("INSERT INTO events VALUES ('ev_1', 'p_00001', 31, 'CALL', NULL, NULL, NULL, NULL, "
                    "'mmg_001', '020030', 'agent_action', 'act_s1_agents_1')")
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO events VALUES ('ev_2', 'p_00001', 31, 'PHONE', NULL, NULL, NULL, NULL, "
                        "'mmg_001', '020030', 'sim', NULL)")
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO audit_log VALUES (31, NULL, 'deleted', 'manager', '{}')")
