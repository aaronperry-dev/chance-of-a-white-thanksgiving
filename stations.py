"""Station source: NOAA NCEI 1991-2020 daily Climate Normals -> chance of >= 1 inch of snow on the ground on Thanksgiving.

NCEI publishes, for every station and every calendar day, ``DLY-SNWD-PCTALL-GE001WI``: the probability (%) that snow
depth is at least 1 inch. NOAA's White Christmas map is that column for Dec 25. Thanksgiving falls on Nov 22-28, so the
default here is the mean of those seven days (see ``config.THANKSGIVING_DAYS``); a single date can be pinned instead.

The by-station archive is ~300 MB (~15,600 CSV files, one per station, about 70 % of which have no snow-depth
columns). It is streamed once and distilled to a small JSON file in ``cache/``; the archive itself is then deleted.

Output columns: id, name, state, lat, lon, elev_m, prob, years     (prob in percent, 0-100)
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import tarfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config as C
from fetch import USER_AGENT, FetchError, ensure_file

log = logging.getLogger(__name__)

_NAME = re.compile(r"^(?P<city>.*?),\s*(?P<st>[A-Z]{2})\s+US$")
_KEEP_UPPER = {"N", "S", "E", "W", "NE", "NW", "SE", "SW", "NNE", "NNW", "SSE", "SSW", "ENE", "ESE",
               "WNW", "WSW", "AP", "AFB", "WSO", "WSFO", "FAA", "II", "III", "IV", "USAF", "CAA"}
_NEEDED = ("STATION", "LATITUDE", "LONGITUDE", "ELEVATION", "NAME", "month", "day", C.SNOW_COL, "years_" + C.SNOW_COL)


def pretty_name(raw: str) -> tuple[str, str]:
    """'NEW BRUNSWICK 3 SE, NJ US' -> ('New Brunswick 3 SE', 'NJ')."""
    raw = (raw or "").strip()
    m = _NAME.match(raw)
    city, st = (m["city"], m["st"]) if m else (raw, "")

    def word(w: str) -> str:
        if w.upper() in _KEEP_UPPER or any(ch.isdigit() for ch in w):
            return w.upper()
        return "-".join(p.capitalize() for p in w.split("-"))

    return " ".join(word(w) for w in city.split()), st


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return float("nan")


def parse_station_csv(text: str, days: list[tuple[int, int]]) -> dict | None:
    """One NCEI daily-normals station file -> a record, or None if it has no usable value.

    A station is kept only if every requested day has a real value (NCEI writes -9999 for "not computed"), at
    least ``MIN_YEARS`` years of record, and it lies inside the CONUS box. ``prob`` is the mean over the days.
    """
    rd = csv.reader(io.StringIO(text))
    header = next(rd, None)
    if not header or C.SNOW_COL not in header:
        return None                                                  # no snow-depth normals for this station
    ix = {h: header.index(h) for h in _NEEDED if h in header}
    if len(ix) != len(_NEEDED):
        return None
    want = set(days)
    vals: dict[tuple[int, int], tuple[float, float]] = {}
    first: list[str] | None = None
    for row in rd:
        if len(row) <= max(ix.values()):
            continue
        if first is None:
            first = row
            west, south, east, north = C.CONUS_BBOX
            lat, lon = _num(row[ix["LATITUDE"]]), _num(row[ix["LONGITUDE"]])
            if not (south <= lat <= north and west <= lon <= east):
                return None                                          # Alaska, Hawaii, territories
        try:
            key = (int(row[ix["month"]]), int(row[ix["day"]]))
        except ValueError:
            continue
        if key in want:
            vals[key] = (_num(row[ix[C.SNOW_COL]]), _num(row[ix["years_" + C.SNOW_COL]]))
    if first is None or set(vals) != want:
        return None
    p = np.array([vals[k][0] for k in days], float)
    y = np.array([vals[k][1] for k in days], float)
    if not (np.isfinite(p).all() and ((p >= 0) & (p <= 100)).all()):
        return None
    if not np.isfinite(y).all() or y.min() < C.MIN_YEARS:
        return None
    elev = _num(first[ix["ELEVATION"]])
    return {"id": first[ix["STATION"]].strip(), "name": first[ix["NAME"]].strip(),
            "lat": _num(first[ix["LATITUDE"]]), "lon": _num(first[ix["LONGITUDE"]]),
            "elev": None if not np.isfinite(elev) or elev < -500 else elev,       # -999.9 = unknown
            "prob": round(float(p.mean()), 2), "years": int(round(float(y.mean())))}


def distill_archive(path: Path, days: list[tuple[int, int]]) -> list[dict]:
    """Stream the by-station .tar.gz and return one record per usable station."""
    recs: list[dict] = []
    seen = 0
    try:
        with tarfile.open(path, mode="r|gz") as tf:                 # stream mode: one pass, no seeking
            for m in tf:
                if not (m.isfile() and m.name.endswith(".csv")):
                    continue
                seen += 1
                fh = tf.extractfile(m)
                rec = parse_station_csv(fh.read().decode("utf-8", "replace"), days) if fh else None
                if rec:
                    recs.append(rec)
                if seen % 3000 == 0:
                    log.info("read %d station files, %d usable so far", seen, len(recs))
    except (tarfile.TarError, EOFError, OSError) as exc:
        raise FetchError(f"{Path(path).name} is not a complete .tar.gz archive ({exc})") from exc
    if seen == 0:
        raise FetchError(f"{Path(path).name} contains no station .csv files")
    log.info("%d of %d station files have a usable value for %s", len(recs), seen, C.date_label(days))
    return recs


def check_is_gzip(path: Path) -> None:
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head[:2] != b"\x1f\x8b":
        raise FetchError(f"{Path(path).name} is not a gzip archive (starts with {head!r})")


def archive_url() -> str:
    """Newest by-station archive listed on NCEI's directory page (the file name carries a creation date)."""
    try:
        r = requests.get(C.NORMALS_DIR_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        names = sorted(set(re.findall(C.NORMALS_ARCHIVE_PATTERN, r.text)))
        if names:
            return C.NORMALS_DIR_URL + names[-1]
    except requests.RequestException as exc:
        log.warning("could not read %s (%s); using the known file name", C.NORMALS_DIR_URL, exc)
    return C.NORMALS_ARCHIVE_URL


def cache_file(days: list[tuple[int, int]]) -> Path:
    tag = "-".join(f"{m:02d}{d:02d}" for m, d in (min(days), max(days))) if len(days) > 1 else f"{days[0][0]:02d}{days[0][1]:02d}"
    return C.RAW_DIR / f"stations_{tag}.json"


def to_frame(recs: list[dict]) -> pd.DataFrame:
    names = [pretty_name(r["name"]) for r in recs]
    out = pd.DataFrame({
        "id": [r["id"] for r in recs],
        "name": [n for n, _ in names], "state": [s for _, s in names],
        "lat": [r["lat"] for r in recs], "lon": [r["lon"] for r in recs],
        "elev_m": [np.nan if r.get("elev") is None else r["elev"] for r in recs],
        "prob": [r["prob"] for r in recs],
        "years": [r.get("years") for r in recs],
    })
    out["prob"] = pd.to_numeric(out["prob"], errors="coerce").clip(0, 100)
    out = out.dropna(subset=["lat", "lon", "prob"]).drop_duplicates(subset=["id"])
    return out.reset_index(drop=True)


def load(days: list[tuple[int, int]] | None = None, *, refresh: bool = False, archive: Path | None = None,
         cache: Path | None = None) -> pd.DataFrame:
    """Stations for ``days`` from the cache, else from ``archive`` (a local .tar.gz), else downloaded from NCEI."""
    days = sorted(days or C.THANKSGIVING_DAYS)
    cache = Path(cache) if cache else cache_file(days)
    if cache.exists() and not refresh and not archive:
        try:
            blob = json.loads(cache.read_text())
            if blob.get("days") == [list(d) for d in days] and blob.get("stations"):
                log.info("using cached %s", cache)
                return to_frame(blob["stations"])
            log.warning("cached %s is for other dates; rebuilding it", cache)
        except (ValueError, OSError) as exc:
            log.warning("cached %s is unreadable (%s); rebuilding it", cache, exc)

    own_download = archive is None
    if archive is None:
        archive = ensure_file(archive_url(), C.RAW_DIR / C.NORMALS_ARCHIVE_FILE, min_bytes=50_000_000, validate=check_is_gzip)
    recs = distill_archive(Path(archive), days)
    if own_download:
        Path(archive).unlink(missing_ok=True)                        # 300 MB; the distilled file is all that is kept
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"days": [list(d) for d in days], "source": C.SOURCE_PAGE, "stations": recs},
                                separators=(",", ":")))
    df = to_frame(recs)
    log.info("%d stations from NOAA NCEI daily normals", len(df))
    return df
