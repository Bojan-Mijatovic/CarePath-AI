"""Reference data for the simulator: the comuni of ATS Val Padana, their ASST and their population.

Delivery plan step 1.10; sources and numbers in src/sim/README.md. Downloads the ISTAT files,
assigns every comune to an ASST, checks the result against ISTAT's own province totals and writes:

    src/sim/data/comuni.csv             one row per comune: SPEC §3.2 `comuni` without lat/lon (step 1.11)
    src/sim/data/population_by_age.csv  comune × sex × 5-year age band; age_to is empty for 100 and over
    src/sim/data/sources.csv            URL, licence and SHA-256 of every input

    uv run carepath-reference-data [--refresh]
"""

import argparse
import hashlib
import io
import re
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"
ISTAT_LICENCE = "CC BY 4.0, https://www.istat.it/note-legali/"
SOURCES = {
    "comuni": "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv",
    "posas_comuni": "https://demo.istat.it/data/posas/POSAS_2025_it_Comuni.zip",
    "posas_province": "https://demo.istat.it/data/posas/POSAS_2025_it_Province.zip",
}
ATS_CREMONA_URL = "https://ats-valpadana.it/system/files/news/files/711/1166/Elenco%20Comuni%20ASST%20Cremona.pdf"
ATS_CREMONA_LIST = DATA_DIR / "asst_cremona_comuni.csv"  # transcribed from the ATS PDF of 27 Mar 2022

# ASST Mantova is the province of Mantova. The province of Cremona splits into ASST Cremona (the ATS
# list) and ASST Crema (everything else).
PROVINCES = {"MN": "020", "CR": "019"}


def norm(name: str) -> str:
    """Name key that ignores accents, case, spaces and punctuation ("Ed Uniti" == "ed Uniti")."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", ascii_name.lower())


def download(url: str, refresh: bool = False) -> Path:
    path = RAW_DIR / url.rsplit("/", 1)[-1]
    if refresh or not path.exists():
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as resp:
            path.write_bytes(resp.read())
    return path


def read_comuni(path: Path) -> pd.DataFrame:
    """ISTAT list of comuni, restricted to the provinces of ATS Val Padana."""
    df = pd.read_csv(path, sep=";", encoding="latin1", dtype=str)
    code = next(c for c in df.columns if c.startswith("Codice Comune formato alfanumerico"))
    sigla = next(c for c in df.columns if c.startswith("Sigla automobilistica"))
    df = df.loc[df[sigla].isin(PROVINCES), [code, "Denominazione in italiano", sigla]]
    df.columns = ["comune_istat", "name", "province"]
    return df.reset_index(drop=True)


def read_posas(path: Path) -> pd.DataFrame:
    """ISTAT POSAS file (zip with one CSV) as columns code, age, males, females; drops the total row."""
    with zipfile.ZipFile(path) as zf:
        raw = zf.read(zf.namelist()[0])
    df = pd.read_csv(io.BytesIO(raw), sep=";", skiprows=1, encoding="utf-8-sig", dtype=str)
    df = pd.DataFrame({"code": df.iloc[:, 0], "age": df.iloc[:, 2].astype(int),
                       "males": df["Totale maschi"].astype(int), "females": df["Totale femmine"].astype(int)})
    return df[df.age != 999].reset_index(drop=True)


def assign_asst(comuni: pd.DataFrame, cremona_names: list[str]) -> pd.Series:
    """ASST of every comune. Fails if a name on the ATS list is not an ISTAT comune of the province."""
    keys = comuni.name.map(norm)
    in_cremona_list = keys.isin({norm(n) for n in cremona_names}) & (comuni.province == "CR")
    unknown = {norm(n) for n in cremona_names} - set(keys[comuni.province == "CR"])
    if unknown:
        raise ValueError(f"ATS list names not found among ISTAT comuni of Cremona: {sorted(unknown)}")
    asst = pd.Series("asst_crema", index=comuni.index)
    asst[comuni.province == "MN"] = "asst_mantova"
    asst[in_cremona_list] = "asst_cremona"
    return asst


def age_bands(pop: pd.DataFrame) -> pd.DataFrame:
    """Single years of age to 5-year bands; ISTAT's age 100 means 100 and over."""
    age_from = (pop.age // 5 * 5).clip(upper=100)
    age_to = (age_from + 4).where(age_from < 100).astype("Int64")
    long = pop.assign(age_from=age_from, age_to=age_to).melt(
        id_vars=["code", "age_from", "age_to"], value_vars=["males", "females"], var_name="sex",
        value_name="population")
    long["sex"] = long.sex.map({"males": "M", "females": "F"})
    out = long.groupby(["code", "sex", "age_from", "age_to"], dropna=False, as_index=False).population.sum()
    return out.rename(columns={"code": "comune_istat"}).sort_values(["comune_istat", "sex", "age_from"])


def check_province_totals(pop: pd.DataFrame, comuni: pd.DataFrame, provinces: pd.DataFrame) -> None:
    """The comuni of each province, summed per age and sex, must equal ISTAT's province file."""
    summed = (pop.merge(comuni[["comune_istat", "province"]], left_on="code", right_on="comune_istat")
                 .groupby(["province", "age"])[["males", "females"]].sum())
    for sigla, code in PROVINCES.items():
        official = provinces[provinces.code == code].set_index("age")[["males", "females"]].sort_index()
        if not summed.loc[sigla].equals(official):
            raise ValueError(f"comuni of {sigla} do not add up to ISTAT's province totals")


def build(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    paths = {key: download(url, refresh) for key, url in SOURCES.items()}
    comuni = read_comuni(paths["comuni"])
    comuni["asst_id"] = assign_asst(comuni, pd.read_csv(ATS_CREMONA_LIST).name.tolist())
    pop = read_posas(paths["posas_comuni"])
    pop = pop[pop.code.isin(comuni.comune_istat)]
    check_province_totals(pop, comuni, read_posas(paths["posas_province"]))

    total = pop.males + pop.females
    per_comune = pd.DataFrame({"code": pop.code, "population": total,
                               "population_65plus": total.where(pop.age >= 65, 0)}).groupby("code").sum()
    comuni_out = (comuni.merge(per_comune, left_on="comune_istat", right_index=True, validate="1:1")
                        [["comune_istat", "name", "asst_id", "population", "population_65plus"]]
                        .sort_values("comune_istat"))

    sources = pd.DataFrame([
        {"source": key, "url": url, "licence": ISTAT_LICENCE,
         "sha256": hashlib.sha256(paths[key].read_bytes()).hexdigest()} for key, url in SOURCES.items()
    ] + [{"source": "ats_asst_cremona", "url": ATS_CREMONA_URL,
          "licence": "public document; names transcribed to asst_cremona_comuni.csv", "sha256": ""}])
    return comuni_out, age_bands(pop), sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the simulator's reference data (delivery plan, step 1.10).")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args()
    comuni, population, sources = build(args.refresh)
    for name, df in [("comuni", comuni), ("population_by_age", population), ("sources", sources)]:
        df.to_csv(DATA_DIR / f"{name}.csv", index=False, lineterminator="\n")
    print(comuni.groupby("asst_id").agg(comuni=("comune_istat", "size"), population=("population", "sum"),
                                        population_65plus=("population_65plus", "sum")).to_string())


if __name__ == "__main__":
    main()
