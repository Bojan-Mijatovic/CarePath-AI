"""Risk model: the chance of an unplanned admission in the next 30 days (delivery plan step 2.3, SPEC §5.1).

An XGBoost classifier, trained once offline on a seed the demo never uses (TRAIN_SEED) and on the
simulator without a scenario, so it cannot learn where the hidden patterns are; training gives the same
bytes every time, and the model file is versioned in models/. Features come from the state engine's
arrays, the same code in training and on a tick, and are named from the pathway (AC17): days since the
last dispense of each of its drugs, not "furosemide". The top 3 drivers of a high-risk patient are the
features with the largest positive contribution (XGBoost's own TreeSHAP, `pred_contribs`); other
patients have none.

The 30-day outcome of the simulator is mostly chance: its own hazard ranks patients with an AUC of 0.62,
and the model reaches the same on a held-out seed (testing/notebooks/risk.ipynb). HIGH_RISK picks about
the top 1% (D37).

`RiskModel.update(con, state, day)` scores every patient on the tick (SPEC §9 step 3) and writes
risk_score and risk_drivers where they changed.

    uv run python -m engine.risk   # retrain and rewrite models/risk_<pathway_id>.json
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import xgboost as xgb

from engine import pathway as pathway_model
from engine.db import create_run, open_run
from engine.pathway import Pathway
from engine.state import NO_DAY, StateEngine

MODELS_DIR = Path(__file__).resolve().parents[2] / "models"
MODEL_VERSION = 1
TRAIN_SEED = 7  # the demo runs on seed 42
HORIZON_DAYS = 30
HIGH_RISK = 0.10  # about 115 of 10,000 patients; 21% of the top 1% are admitted within 30 days (D37)
SNAPSHOT_EVERY_DAYS = 7
CAP_DAYS = 365
TOP_DRIVERS = 3
PARAMS = {"objective": "binary:logistic", "eval_metric": "auc", "max_depth": 4, "eta": 0.1, "subsample": 0.8,
          "min_child_weight": 5, "tree_method": "hist", "seed": 0, "nthread": 4}
ROUNDS = 200


def feature_names(pathway: Pathway) -> list[str]:
    return (["age", "distance_km", "lives_alone", "days_since_discharge"]
            + [f"days_since_last_dispense:{atc}" for atc in pathway.eligibility.any_drug_atc]
            + ["on_telemonitoring", "days_since_last_reading", "weight_gain_kg_3d", "overdue_steps", "days_overdue"])


def features(state: StateEngine, day: int) -> np.ndarray:
    """One row per patient (state.ids order), columns as feature_names; NaN where a value does not exist."""
    def since(last):
        return np.where(last > NO_DAY, np.minimum(day - last, CAP_DAYS), np.nan)
    start = state.own[state.starts].max(axis=0) if state.starts else np.full(len(state.ids), NO_DAY)
    columns = ([state.age, state.distance_km, state.lives_alone, since(start)]
               + [since(last) for last in state.last_drug]
               + [state.telemon_started, np.where(state.telemon_started, since(state.last_reading), np.nan),
                  state.weight_gain_kg_3d(day), state.n_overdue, state.days_overdue])
    return np.column_stack(columns).astype(np.float32)


class RiskModel:
    def __init__(self, pathway: Pathway, path: Path | None = None):
        self.pathway = pathway
        self.path = path or MODELS_DIR / f"risk_{pathway.pathway_id}.json"
        self.booster = xgb.Booster()
        self.booster.load_model(self.path)
        self.names = feature_names(pathway)
        if json.loads(self.booster.attr("features")) != self.names:
            raise ValueError(f"{self.path} was trained on other features; retrain with python -m engine.risk")
        self.written: tuple[np.ndarray, np.ndarray] | None = None  # scores and driver indexes as last written
        self.risk: np.ndarray | None = None  # every patient's score and driver indexes on the last update
        self.top: np.ndarray | None = None

    def score(self, state: StateEngine, day: int) -> tuple[np.ndarray, np.ndarray]:
        """(risk per patient rounded as SPEC §2, top driver indexes per patient with -1 for none). Drivers
        are computed for high-risk patients only: TreeSHAP for all 10,000 took 500 ms a tick against 12 ms
        for the top 1%, and the faster approximation agreed on the top 3 for only half of them."""
        x = features(state, day)
        risk = self.booster.predict(xgb.DMatrix(x, feature_names=self.names)).astype(np.float64).round(4)
        top = np.full((len(risk), TOP_DRIVERS), -1)
        high = np.flatnonzero(risk >= HIGH_RISK)
        if len(high):
            contrib = self.booster.predict(xgb.DMatrix(x[high], feature_names=self.names), pred_contribs=True)[:, :-1]
            best = np.argsort(-contrib, axis=1, kind="stable")[:, :TOP_DRIVERS]  # the last column was the bias
            top[high] = np.where(np.take_along_axis(contrib, best, axis=1) > 0, best, -1)
        return risk, top

    def drivers(self, top: np.ndarray) -> list[list[str]]:
        return [[self.names[j] for j in row if j >= 0] for row in top]

    def update(self, con: duckdb.DuckDBPyConnection, state: StateEngine, day: int) -> int:
        """Score everyone and write risk_score, and risk_drivers only where they changed (a list column
        costs a whole-row rewrite, as for overdue_steps). Returns how many rows changed."""
        risk, top = self.score(state, day)
        self.risk, self.top = risk, top
        old_risk, old_top = self.written or (np.full_like(risk, -1.0), np.full_like(top, -2))
        enrolled = state.enrolled_day <= day
        new_risk = enrolled & (risk != old_risk)
        new_top = enrolled & (top != old_top).any(axis=1)
        self.written = (np.where(enrolled, risk, old_risk), np.where(enrolled[:, None], top, old_top))
        for rows, column in [(new_risk, "risk_score"), (new_top, "risk_drivers")]:
            idx = np.flatnonzero(rows)
            if len(idx):
                value = risk[idx] if column == "risk_score" else self.drivers(top[idx])  # lists only where needed
                con.register("risk_rows", pd.DataFrame({"patient_id": state.ids[idx], column: value}))
                con.execute(f"UPDATE pathway_state s SET {column} = r.{column} FROM risk_rows r "
                            "WHERE s.patient_id = r.patient_id AND s.pathway_id = $pathway",
                            {"pathway": self.pathway.pathway_id})
                con.unregister("risk_rows")
        return int((new_risk | new_top).sum())


def dataset(seed: int, scenario: int | None, pathway: Pathway, days: int = 365) -> pd.DataFrame:
    """Weekly snapshots of every enrolled patient out of hospital, with the label "unplanned admission in
    the next 30 days". The simulator runs without agents; `scenario=None` runs it without patterns.
    `hazard` is the simulator's own daily hazard on the snapshot day: never a feature, only the ceiling a
    model can reach (testing/notebooks/risk.ipynb)."""
    from sim.population import generate_patients, load_reference  # training only; agents never import sim
    from sim.run import append, load_reference_tables
    from sim.step import Simulator, load_scenario

    ref = load_reference()
    patients, mmg = generate_patients(seed, ref)
    sim = Simulator(seed, patients, ref, pathway, days=days)
    if scenario is not None:
        sim.apply_scenario(load_scenario(scenario), mmg)
    tmp = Path(tempfile.mkdtemp())
    try:
        create_run(f"s{scenario or 1}_baseline", runs_dir=tmp)
        with open_run(f"s{scenario or 1}_baseline", tmp) as con:
            load_reference_tables(con, ref, patients, mmg)
            for events in sim.warm_up():
                append(con, "events", events)
            state = StateEngine(con, pathway)
            frames = []
            for d in range(days):
                append(con, "events", sim.step(d))
                state.update(con, d)
                if d % SNAPSHOT_EVERY_DAYS == 0 and d + HORIZON_DAYS < days:
                    keep = (state.enrolled_day <= d) & ~state.in_hospital()
                    f = pd.DataFrame(features(state, d)[keep], columns=feature_names(pathway))
                    frames.append(f.assign(patient_id=state.ids[keep], day=d, hazard=sim.hazard(d)[keep]))
            admissions = con.execute("SELECT patient_id, day FROM events WHERE event_type = 'ADMISSION' "
                                     "AND value = 1 AND day >= 0").df()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    data = pd.concat(frames, ignore_index=True)
    pairs = data[["patient_id", "day"]].merge(admissions, on="patient_id", suffixes=("", "_adm"))
    hit = pairs[(pairs.day_adm > pairs.day) & (pairs.day_adm <= pairs.day + HORIZON_DAYS)]
    data["label"] = data.set_index(["patient_id", "day"]).index.isin(hit.set_index(["patient_id", "day"]).index)
    return data


def train(pathway: Pathway, data: pd.DataFrame) -> xgb.Booster:
    names = feature_names(pathway)
    booster = xgb.train(PARAMS, xgb.DMatrix(data[names].to_numpy(np.float32), label=data.label, feature_names=names),
                        num_boost_round=ROUNDS)
    booster.set_attr(features=json.dumps(names), pathway_id=pathway.pathway_id, version=str(MODEL_VERSION),
                     train_seed=str(TRAIN_SEED), horizon_days=str(HORIZON_DAYS))
    return booster


def auc(booster: xgb.Booster, pathway: Pathway, data: pd.DataFrame) -> float:
    from sklearn.metrics import roc_auc_score  # training and notebooks only
    names = feature_names(pathway)
    return float(roc_auc_score(data.label, booster.predict(xgb.DMatrix(data[names].to_numpy(np.float32),
                                                                       feature_names=names))))


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the risk model (delivery plan, step 2.3).")
    parser.add_argument("--pathway", default="hf_lombardia_v1")
    args = parser.parse_args()
    pathway = pathway_model.load(args.pathway)
    data = dataset(TRAIN_SEED, None, pathway)
    print(f"training: {len(data)} snapshots, {data.label.mean():.1%} admitted within {HORIZON_DAYS} days")
    booster = train(pathway, data)
    MODELS_DIR.mkdir(exist_ok=True)
    path = MODELS_DIR / f"risk_{pathway.pathway_id}.json"
    booster.save_model(path)
    print(path)
    print(f"AUC on the training seed: {auc(booster, pathway, data):.3f}; held-out seeds: testing/notebooks/risk.ipynb")


if __name__ == "__main__":
    main()
