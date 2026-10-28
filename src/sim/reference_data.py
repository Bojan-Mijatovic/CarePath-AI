"""Reference data for the simulator: the comuni of ATS Val Padana, their ASST, population and boundaries.

Delivery plan steps 1.10 and 1.11; sources and numbers in src/sim/README.md. Downloads the ISTAT files,
assigns every comune to an ASST, checks the result against ISTAT's own province totals and writes:

    src/sim/data/comuni.csv             one row per comune: SPEC §3.2 `comuni`; lat/lon is the area centroid
    src/sim/data/population_by_age.csv  comune × sex × 5-year age band; age_to is empty for 100 and over
    src/sim/data/sources.csv            URL, licence and SHA-256 of every input
    src/ui/assets/comuni.geojson        comune boundaries for the console map (WGS84, RFC 7946 winding)

    uv run carepath-reference-data [--refresh]
"""

import argparse
import hashlib
import io
import json
import re
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd
import shapefile
from pyproj import Transformer

DATA_DIR = Path(__file__).resolve().parent / "data"
RAW_DIR = DATA_DIR / "raw"
GEOJSON_PATH = Path(__file__).resolve().parents[1] / "ui" / "assets" / "comuni.geojson"
ISTAT_LICENCE = "CC BY 4.0, https://www.istat.it/note-legali/"
SOURCES = {
    "comuni": "https://www.istat.it/storage/codici-unita-amministrative/Elenco-comuni-italiani.csv",
    "posas_comuni": "https://demo.istat.it/data/posas/POSAS_2025_it_Comuni.zip",
    "posas_province": "https://demo.istat.it/data/posas/POSAS_2025_it_Province.zip",
    "boundaries": "https://www.istat.it/storage/cartografia/confini_amministrativi/generalizzati/2026/Limiti01012026_g.zip",
}
BOUNDARIES_LAYER = "Com01012026_g/Com01012026_g_WGS84"  # ISTAT names it WGS84, but it is UTM 32N
UTM32N_TO_WGS84 = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)
COORD_DECIMALS = 5  # about 1 m
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


def read_boundaries(path: Path, codes: set[str]) -> dict[str, list[list[tuple[float, float]]]]:
    """Rings (UTM 32N metres) of every comune in `codes`, from the ISTAT boundaries zip."""
    with zipfile.ZipFile(path) as zf:
        parts = {ext: io.BytesIO(zf.read(f"{BOUNDARIES_LAYER}.{ext}")) for ext in ("shp", "shx", "dbf")}
    rings = {}
    with shapefile.Reader(**parts) as reader:
        for rec in reader.iterShapeRecords(fields=["PRO_COM_T"]):
            code = rec.record["PRO_COM_T"]
            if code in codes:
                pts, starts = rec.shape.points, list(rec.shape.parts) + [len(rec.shape.points)]
                rings[code] = [[tuple(p) for p in pts[a:b]] for a, b in zip(starts, starts[1:])]
    missing = codes - set(rings)
    if missing:
        raise ValueError(f"no ISTAT boundary for comuni {sorted(missing)}")
    return rings


def signed_area(ring: list[tuple[float, float]]) -> float:
    """Shoelace formula; positive for counter-clockwise rings."""
    return sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:])) / 2


def centroid(rings: list[list[tuple[float, float]]]) -> tuple[float, float]:
    """Area centroid of a comune; holes count negatively. Computed relative to the first point, because
    UTM coordinates are millions of metres and the shoelace products would lose precision."""
    ox, oy = rings[0][0]
    rings = [[(x - ox, y - oy) for x, y in ring] for ring in rings]
    total, cx, cy = 0.0, 0.0, 0.0
    outer_sign = 1 if signed_area(max(rings, key=lambda r: abs(signed_area(r)))) > 0 else -1
    for ring in rings:
        a = signed_area(ring) * outer_sign
        for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
            cross = (x0 * y1 - x1 * y0) * outer_sign
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        total += a
    return ox + cx / (6 * total), oy + cy / (6 * total)


def to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon, lat = UTM32N_TO_WGS84.transform(x, y)
    return round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS)


def geometry(rings: list[list[tuple[float, float]]]) -> dict:
    """GeoJSON MultiPolygon. Shapefile outer rings are clockwise and holes counter-clockwise, and a hole
    follows its outer ring; RFC 7946 wants the opposite winding, so every ring is reversed."""
    polygons: list[list[list[tuple[float, float]]]] = []
    for ring in rings:
        lonlat = [to_lonlat(x, y) for x, y in reversed(ring)]
        if signed_area(ring) < 0:  # clockwise in the shapefile: an outer ring
            polygons.append([lonlat])
        elif polygons:
            polygons[-1].append(lonlat)
        else:
            raise ValueError("shapefile shape starts with a hole")
    return {"type": "MultiPolygon", "coordinates": polygons}


def build(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    paths = {key: download(url, refresh) for key, url in SOURCES.items()}
    comuni = read_comuni(paths["comuni"])
    comuni["asst_id"] = assign_asst(comuni, pd.read_csv(ATS_CREMONA_LIST).name.tolist())
    pop = read_posas(paths["posas_comuni"])
    pop = pop[pop.code.isin(comuni.comune_istat)]
    check_province_totals(pop, comuni, read_posas(paths["posas_province"]))

    total = pop.males + pop.females
    per_comune = pd.DataFrame({"code": pop.code, "population": total,
                               "population_65plus": total.where(pop.age >= 65, 0)}).groupby("code").sum()
    rings = read_boundaries(paths["boundaries"], set(comuni.comune_istat))
    centroids = {code: to_lonlat(*centroid(r)) for code, r in rings.items()}
    comuni["lon"] = comuni.comune_istat.map(lambda c: centroids[c][0])
    comuni["lat"] = comuni.comune_istat.map(lambda c: centroids[c][1])
    comuni_out = (comuni.merge(per_comune, left_on="comune_istat", right_index=True, validate="1:1")
                        [["comune_istat", "name", "asst_id", "population", "population_65plus", "lat", "lon"]]
                        .sort_values("comune_istat"))
    geojson = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"comune_istat": row.comune_istat, "name": row.name, "asst_id": row.asst_id},
         "geometry": geometry(rings[row.comune_istat])} for row in comuni_out.itertuples()]}

    sources = pd.DataFrame([
        {"source": key, "url": url, "licence": ISTAT_LICENCE,
         "sha256": hashlib.sha256(paths[key].read_bytes()).hexdigest()} for key, url in SOURCES.items()
    ] + [{"source": "ats_asst_cremona", "url": ATS_CREMONA_URL,
          "licence": "public document; names transcribed to asst_cremona_comuni.csv", "sha256": ""}])
    return comuni_out, age_bands(pop), sources, geojson


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the simulator's reference data (delivery plan, steps 1.10-1.11).")
    parser.add_argument("--refresh", action="store_true", help="download the sources again")
    args = parser.parse_args()
    comuni, population, sources, geojson = build(args.refresh)
    for name, df in [("comuni", comuni), ("population_by_age", population), ("sources", sources)]:
        df.to_csv(DATA_DIR / f"{name}.csv", index=False, lineterminator="\n")
    GEOJSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOJSON_PATH.write_text(json.dumps(geojson, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8",
                            newline="\n")
    print(f"{GEOJSON_PATH.name}: {GEOJSON_PATH.stat().st_size / 1e6:.2f} MB")
    print(comuni.groupby("asst_id").agg(comuni=("comune_istat", "size"), population=("population", "sum"),
                                        population_65plus=("population_65plus", "sum")).to_string())


if __name__ == "__main__":
    main()
