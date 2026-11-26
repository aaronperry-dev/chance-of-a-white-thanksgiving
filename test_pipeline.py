"""Pipeline tests.

Fixtures are SYNTHETIC: the station CSV text mimics the layout of NCEI's daily-normals files. Nothing here needs the
network.
"""
import csv
import gzip
import io
import json
import os
import tarfile

import numpy as np
import pytest

import config as C
import stations as S
from build import station_stats
from webvec import rdp


# ============================================================ legend
def test_legend_classes_for_thanksgiving():
    assert C.class_labels() == ["0–5%", "6–10%", "11–20%", "21–30%",
                                "31–40%", "41–50%", "51–70%", "71–100%"]
    assert len(C.NOAA_COLORS) == 8 and all(c.startswith("#") and len(c) == 7 for c in C.NOAA_COLORS)


def test_class_index_upper_edge_is_inclusive():
    cases = {0: 0, 5: 0, 5.5: 1, 6: 1, 10: 1, 10.1: 2, 20: 2, 20.5: 3, 30: 3, 40: 4, 50: 5, 70: 6, 71: 7, 100: 7}
    assert {p: C.class_index(p) for p in cases} == cases


def test_station_stats_shares():
    s = station_stats(np.array([0, 5, 10, 11, 25, 30, 95, 100.0]))
    assert s["basis"] == "stations" and s["n"] == 8
    assert sum(s["share_by_class"]) == pytest.approx(1.0)
    assert (C.KPI_HIGH_PCT, C.KPI_LOW_PCT) == (25, 10)
    assert s["share_high"] == pytest.approx(4 / 8) and s["share_low"] == pytest.approx(3 / 8)


# ============================================================ dates
def test_default_window_is_the_seven_possible_thanksgiving_dates():
    assert C.THANKSGIVING_DAYS == [(11, d) for d in range(22, 29)]
    assert C.date_label(C.THANKSGIVING_DAYS) == "Nov 22–28"
    assert C.date_label([(11, 26)]) == "Nov 26"
    assert C.parse_day("11-26") == (11, 26) and C.parse_day("11/5") == (11, 5)
    for bad in ("26", "13-01", "11-40", "nov-26"):
        with pytest.raises(ValueError):
            C.parse_day(bad)


# ============================================================ NOAA tile grid / projection
def test_tile_grid_matches_service_metadata():
    # ArcGIS: resolution = scale * 0.0254 / 96 (96 dpi) to within ~2 ppm (it uses a slightly different inch);
    # the scales are the NOAA service's published LOD scales
    scales = [2.6e7, 1.3e7, 7.5e6, 3.75e6, 1.875e6]
    assert C.TILE_RESOLUTIONS == pytest.approx([s * 0.0254 / 96 for s in scales], rel=1e-5)
    assert C.TILE_SIZE == 256 and len(C.TILE_RESOLUTIONS) == 5
    # the page's view extent lies to the east and south of the tile grid's top-left origin
    x0, y0, x1, y1 = C.NOAA_EXTENT
    assert x0 > C.TILE_ORIGIN[0] and y1 < C.TILE_ORIGIN[1]


def test_lcc_matches_noaa_projection_definition():
    from pyproj import Transformer
    assert "+lat_0=40" in C.LCC_PROJ and "+lon_0=-96" in C.LCC_PROJ
    assert "+lat_1=20" in C.LCC_PROJ and "+lat_2=60" in C.LCC_PROJ
    t = Transformer.from_crs("EPSG:4326", C.LCC_PROJ, always_xy=True)
    assert t.transform(-96.0, 40.0) == pytest.approx((0, 0), abs=1e-6)
    assert t.transform(-122.3, 47.6) == pytest.approx((-1841985, 1074564), abs=3)   # Seattle (also checked in the browser)


# ============================================================ NCEI daily normals
def station_csv(sid="USC00144665", name="LEOTI, KS US", lat=38.49, lon=-101.3669, elev=1008.6,
                value=lambda m, d: 8.0, years=lambda m, d: 27, skip_col=False, dates=None):
    """Text shaped like NCEI's per-station daily-normals file (only the columns the loader reads, plus noise)."""
    col = "DLY-SNWD-PCTALL-GE001WI"
    cols = ["STATION", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION", "NAME", "month", "day", "hour", "DLY-TAVG-NORMAL"]
    if not skip_col:
        cols += [col, "meas_flag_" + col, "comp_flag_" + col, "years_" + col]
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_NONNUMERIC)
    w.writerow(cols)
    for m, d in (dates or [(11, x) for x in range(18, 31)] + [(12, 25)]):
        row = [sid, f"{m:02d}-{d:02d}", lat, lon, elev, name, m, d, 24, 40.1]
        if not skip_col:
            v = value(m, d)
            row += [v, "", "S" if v != -9999 else "", years(m, d)]
        w.writerow(row)
    return out.getvalue()


def test_parse_station_averages_the_thanksgiving_window():
    rec = S.parse_station_csv(station_csv(value=lambda m, d: float(d)), C.THANKSGIVING_DAYS)     # 22..28 -> mean 25
    assert rec["id"] == "USC00144665" and rec["prob"] == pytest.approx(25.0) and rec["years"] == 27
    assert rec["elev"] == pytest.approx(1008.6) and rec["lat"] == 38.49
    one = S.parse_station_csv(station_csv(value=lambda m, d: float(d)), [(11, 26)])
    assert one["prob"] == 26.0                                                                       # a pinned date


def test_parse_station_drops_unusable_stations():
    days = C.THANKSGIVING_DAYS
    assert S.parse_station_csv(station_csv(skip_col=True), days) is None                           # no snow-depth normals
    assert S.parse_station_csv(station_csv(value=lambda m, d: -9999.0), days) is None             # "not computed"
    assert S.parse_station_csv(station_csv(value=lambda m, d: -9999.0 if d == 25 else 8.0), days) is None   # one day missing
    assert S.parse_station_csv(station_csv(years=lambda m, d: 4), days) is None                    # too short a record
    assert S.parse_station_csv(station_csv(lat=61.2, lon=-149.9), days) is None                    # Anchorage: outside CONUS
    assert S.parse_station_csv(station_csv(dates=[(11, 22), (11, 23)]), days) is None              # window not in the file
    assert S.parse_station_csv("", days) is None


def test_parse_station_unknown_elevation_becomes_none():
    assert S.parse_station_csv(station_csv(elev=-999.9), C.THANKSGIVING_DAYS)["elev"] is None


def test_pretty_name():
    assert S.pretty_name("LEOTI, KS US") == ("Leoti", "KS")
    assert S.pretty_name("NEW BRUNSWICK 3 SE, NJ US") == ("New Brunswick 3 SE", "NJ")
    assert S.pretty_name("WINSTON-SALEM REYNOLDS AP, NC US") == ("Winston-Salem Reynolds AP", "NC")
    assert S.pretty_name("WEIRD NAME") == ("Weird Name", "")


def make_archive(path, files: dict[str, str], member_dir="by-station/"):
    with tarfile.open(path, "w:gz") as tf:
        for name, text in files.items():
            data = text.encode()
            ti = tarfile.TarInfo(member_dir + name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))


def test_distill_archive_streams_all_members(tmp_path):
    p = tmp_path / "n.tar.gz"
    make_archive(p, {
        "A.csv": station_csv("A", "ALPHA, MN US", 45.0, -93.2, 250, value=lambda m, d: 20.0),
        "B.csv": station_csv("B", "BRAVO, CO US", 39.7, -105.0, 1600, value=lambda m, d: 60.0),
        "C.csv": station_csv("C", "CHARLIE, TX US", 31.0, -97.0, 150, skip_col=True),
        "README.txt": "not a station",
    })
    recs = S.distill_archive(p, C.THANKSGIVING_DAYS)
    assert [r["id"] for r in recs] == ["A", "B"]
    df = S.to_frame(recs)
    assert df.columns.tolist() == ["id", "name", "state", "lat", "lon", "elev_m", "prob", "years"]
    assert df.loc[1, ["name", "state"]].tolist() == ["Bravo", "CO"] and df.prob.tolist() == [20.0, 60.0]


def test_distill_archive_rejects_broken_files(tmp_path):
    bad = tmp_path / "x.tar.gz"
    bad.write_bytes(b"<html>not an archive</html>" * 10)
    with pytest.raises(S.FetchError):
        S.distill_archive(bad, C.THANKSGIVING_DAYS)
    empty = tmp_path / "e.tar.gz"
    make_archive(empty, {"notes.txt": "x"})
    with pytest.raises(S.FetchError, match="no station"):
        S.distill_archive(empty, C.THANKSGIVING_DAYS)
    whole = tmp_path / "w.tar.gz"
    make_archive(whole, {"A.csv": station_csv("A") * 200})
    cut = tmp_path / "cut.tar.gz"
    cut.write_bytes(whole.read_bytes()[: whole.stat().st_size // 2])         # a download that stopped half way
    with pytest.raises(S.FetchError):
        S.distill_archive(cut, C.THANKSGIVING_DAYS)


def test_load_from_local_archive_then_cache_without_network(tmp_path, monkeypatch):
    p, cache = tmp_path / "n.tar.gz", tmp_path / "cache" / "s.json"
    make_archive(p, {"A.csv": station_csv("A", "ALPHA, MN US", 45.0, -93.2, 250, value=lambda m, d: 20.0)})
    df = S.load(archive=p, cache=cache)
    assert len(df) == 1 and p.exists() and cache.exists()                     # a hand-placed archive is never deleted
    monkeypatch.setattr(S, "distill_archive", lambda *a, **k: pytest.fail("should read the cache"))
    monkeypatch.setattr(S, "ensure_file", lambda *a, **k: pytest.fail("should not download"))
    assert S.load(cache=cache).prob.tolist() == [20.0]


def test_cache_for_other_dates_is_not_reused(tmp_path):
    p, cache = tmp_path / "n.tar.gz", tmp_path / "s.json"
    make_archive(p, {"A.csv": station_csv("A", value=lambda m, d: float(d))})
    assert S.load([(11, 22)], archive=p, cache=cache).prob.tolist() == [22.0]
    blob = json.loads(cache.read_text())
    assert blob["days"] == [[11, 22]]
    # same cache file asked for another date: rebuilt from the archive instead of silently reused
    assert S.load([(11, 28)], archive=p, cache=cache).prob.tolist() == [28.0]


def test_cache_files_are_named_by_date():
    assert S.cache_file(C.THANKSGIVING_DAYS).name == "stations_1122-1128.json"
    assert S.cache_file([(11, 26)]).name == "stations_1126.json"


def test_downloaded_archive_is_deleted_after_distilling(tmp_path, monkeypatch):
    src, dest = tmp_path / "src.tar.gz", tmp_path / "cache" / "dl.tar.gz"
    make_archive(src, {"A.csv": station_csv("A")})
    monkeypatch.setattr(S, "archive_url", lambda: "http://example.invalid/n.tar.gz")

    def fake_ensure(url, path, **kw):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(src.read_bytes())
        return path

    monkeypatch.setattr(S, "ensure_file", fake_ensure)
    monkeypatch.setattr(S.C, "RAW_DIR", tmp_path / "cache")
    monkeypatch.setattr(S.C, "NORMALS_ARCHIVE_FILE", "dl.tar.gz")
    assert len(S.load(cache=tmp_path / "cache" / "s.json")) == 1
    assert not dest.exists()                                                  # the 300 MB file is not kept


def test_archive_url_follows_the_directory_listing(monkeypatch):
    html = ('<a href="us-climate-normals_1991-2020_v1.0.1_daily_multivariate_by-station_c20230404.tar.gz">a</a>'
            '<a href="us-climate-normals_1991-2020_v1.0.2_daily_multivariate_by-station_c20250101.tar.gz">b</a>'
            '<a href="us-climate-normals_1991-2020_v1.0.1_daily_precipitation_by-variable_c20230404.tar.gz">c</a>')

    class Resp:
        text = html
        def raise_for_status(self): pass

    monkeypatch.setattr(S.requests, "get", lambda *a, **k: Resp())
    assert S.archive_url().endswith("v1.0.2_daily_multivariate_by-station_c20250101.tar.gz")

    def down(*a, **k):
        raise S.requests.ConnectionError("offline")

    monkeypatch.setattr(S.requests, "get", down)
    assert S.archive_url() == C.NORMALS_ARCHIVE_URL                           # falls back to the known file name


def test_rdp_simplifies_but_keeps_shape():
    t = np.linspace(0, 10, 200)
    line = np.column_stack([t, np.zeros_like(t)])
    assert len(rdp(line, 0.01)) == 2
    zig = np.column_stack([t, np.where(np.arange(200) % 2, 1.0, -1.0)])
    assert len(rdp(zig, 0.01)) == 200


# ============================================================ bad download
def test_html_posing_as_gzip_is_rejected_clearly(tmp_path):
    bad = tmp_path / "x.tar.gz"
    bad.write_bytes(b"<!DOCTYPE html><html><body>Not found</body></html>" * 40)
    with pytest.raises(S.FetchError, match="not a gzip"):
        S.check_is_gzip(bad)


def test_ensure_file_never_caches_a_failed_validation_and_replaces_bad_cache(tmp_path, monkeypatch):
    import fetch as F

    class Resp:
        def __init__(self, body): self.body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size): yield self.body

    monkeypatch.setattr(F.time, "sleep", lambda s: None)
    dest = tmp_path / "a.tar.gz"
    monkeypatch.setattr(F.requests, "get", lambda *a, **k: Resp(b"<html>" + b"x" * 2000))
    with pytest.raises(F.FetchError):
        F.ensure_file("http://x", dest, validate=S.check_is_gzip, retries=2)
    assert not dest.exists() and not (tmp_path / "a.tar.gz.part").exists()

    dest.write_bytes(b"<html>" + b"x" * 2000)                           # a bad file already in the cache
    good = gzip.compress(os.urandom(3000))                              # big enough to pass the size check
    monkeypatch.setattr(F.requests, "get", lambda *a, **k: Resp(good))
    out = F.ensure_file("http://x", dest, validate=S.check_is_gzip)
    assert out.read_bytes().startswith(b"\x1f\x8b")
