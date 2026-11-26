"""Central configuration: data sources, projection, grid, terrain, estimation and legend.

Everything the front end needs (tile grid, projection, legend classes and colours)
is written to ``data/meta.json`` from here, so this file is the single
source of truth for the map and the legend.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "cache"      # downloaded inputs (git-ignored; the GitHub Action caches it)
OUT_DIR = ROOT / "data"       # generated site data (git-ignored; the GitHub Action rebuilds it)

# --- What is being mapped ----------------------------------------------------
# U.S. Thanksgiving is the 4th Thursday of November, so it can fall on any date from Nov 22 to Nov 28.
# NOAA's 1991-2020 daily normals give the chance of >= 1 in of snow on the ground for every calendar day;
# by default the map averages the seven possible dates, i.e. "a Thanksgiving whose date is not yet known".
# Pin one date instead with  python build.py --date 11-26  (this year's Thanksgiving is Nov 26, 2026).
EVENT = "Thanksgiving"
THANKSGIVING_DAYS = [(11, d) for d in range(22, 29)]       # (month, day), inclusive window

# --- Stations ----------------------------------------------------------------
# NOAA NCEI 1991-2020 U.S. Climate Normals, DAILY product. Every station file has the column
# DLY-SNWD-PCTALL-GE001WI = probability (%) that snow depth is >= 1 inch on that calendar day
# (the same quantity NOAA maps for Dec 25), plus years_<col> = years of record behind it. The by-station
# archive (~300 MB, ~15,600 files) is streamed once and distilled to a small JSON file in cache/.
NORMALS_DIR_URL = "https://www.ncei.noaa.gov/data/normals-daily/1991-2020/archive/"
NORMALS_ARCHIVE_URL = (NORMALS_DIR_URL +
                       "us-climate-normals_1991-2020_v1.0.1_daily_multivariate_by-station_c20230404.tar.gz")
NORMALS_ARCHIVE_PATTERN = r"us-climate-normals_[0-9-]+_v[0-9.]+_daily_multivariate_by-station[A-Za-z0-9._-]*\.tar\.gz"
NORMALS_ARCHIVE_FILE = "normals_daily_by_station.tar.gz"
SNOW_COL = "DLY-SNWD-PCTALL-GE001WI"
MIN_YEARS = 10          # NCEI only computes the value from >= 10 years; shorter records are blank (-9999)
SOURCE_PAGE = "https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals"

# --- Terrain -----------------------------------------------------------------
# AWS Open Data "Terrain Tiles" (Terrarium PNG encoding, Web Mercator, no key).
TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
DEM_ZOOM = 7  # ~0.8-1.1 km/px over CONUS; 8 is ~2x finer (4x the download)
TERRAIN_CACHE = "terrarium"

# Hillshade (flat terrain renders mid-grey 128 so it can be blended over colour).
HILLSHADE_AZIMUTH = 315.0
HILLSHADE_ALTITUDE = 45.0
HILLSHADE_Z = 4.0     # vertical exaggeration
HILLSHADE_GAIN = 1.0

# --- Boundaries / context (Natural Earth, via GitHub) ------------------------
_NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
BOUNDARY_URL = _NE + "ne_10m_admin_1_states_provinces.geojson"
BOUNDARY_FILE = "ne_10m_admin_1_states_provinces.geojson"
COUNTRIES_URL = _NE + "ne_10m_admin_0_countries.geojson"
COUNTRIES_FILE = "ne_10m_admin_0_countries.geojson"
PLACES_URL = _NE + "ne_50m_populated_places_simple.geojson"
PLACES_FILE = "ne_50m_populated_places_simple.geojson"

NON_CONUS = {
    "Alaska", "Hawaii", "Puerto Rico", "Guam", "American Samoa",
    "United States Virgin Islands", "Northern Mariana Islands",
}
# Station / polygon sanity box (west, south, east, north), degrees.
CONUS_BBOX = (-125.0, 24.0, -66.5, 49.8)

# --- Projection: the same one NOAA's web app and tile service use -----------
# ESRI:102009 "North America Lambert Conformal Conic" (WKID 102009).
LCC_NAME = "ESRI:102009"
LCC_PROJ = ("+proj=lcc +lat_0=40 +lon_0=-96 +lat_1=20 +lat_2=60 "
            "+x_0=0 +y_0=0 +datum=NAD83 +units=m +no_defs")
# NOAA app's constraint extent in LCC metres (xmin, ymin, xmax, ymax). Used to
# frame the view and limit panning.
NOAA_EXTENT = (-3100465.28, -1958797.37, 2987609.40, 1618376.45)

# --- Tile grid of the page's map (NOAA's tile grid for this projection) ------------
# The page's map uses the same zoom levels as NOAA's White Christmas web map, so the images built here are cut
# on that grid (see tiles.py). Values are from the NOAA map service's metadata (tileInfo).
TILE_SIZE = 256
TILE_ORIGIN = (-3.873557170374695e7, 4.6658285798503935e7)   # top-left of the tile grid (LCC m)
TILE_RESOLUTIONS = [6879.180425027517, 3439.5902125137586, 1984.3789687579376,
                    992.1894843789688, 496.0947421894844]    # metres/pixel for LOD 0..4
CREDIT = ("Data: NOAA National Centers for Environmental Information (NCEI), 1991\u20132020 U.S. Climate Normals. "
          "Map style after NOAA Climate.gov's White Christmas map")

# --- Grid --------------------------------------------------------------------
GRID_RES_M = 1000    # pixel size in metres (NOAA's finest service tiles are ~500 m/px)
GRID_PAD_M = 20_000  # margin around CONUS

# Cells with this chance or less are left transparent so the terrain / bathymetry map shows through
# (the map shows every chance greater than 1 %).
TRANSPARENT_AT_OR_BELOW_PCT = 1.0
M_TO_FT = 3.280839895

# --- Base map: land elevation + bathymetry colour ramps -----------------------
# A coarse raster over NOAA's whole view extent (US, Canada, Mexico, oceans, lakes) drawn under the
# probability surface; it is what shows through where the chance is TRANSPARENT_AT_OR_BELOW_PCT or less.
BASE_RES_M = 1000
BASE_PAD_M = 400_000
BASE_DEM_ZOOM = 6          # ~2 km/px at these latitudes (smoothly resampled to BASE_RES_M); coast and lake edges come from the 1:10m vectors
LAKES_URL = _NE + "ne_10m_lakes.geojson"
LAKES_FILE = "ne_10m_lakes.geojson"
# (elevation ft, colour) for land; (depth ft, colour) for ocean and lakes. Light and dark themes.
LAND_RAMP = {
    "light": [(0, "#a8c98f"), (500, "#c3dba0"), (1300, "#e0e6a9"), (2600, "#ecdfa2"), (4300, "#e2c690"),
              (6200, "#cfa77a"), (8500, "#b58863"), (11200, "#9a7160"), (14400, "#d8cfca")],
    "dark": [(0, "#33422d"), (500, "#3d4d33"), (1300, "#4b5338"), (2600, "#575238"), (4300, "#5a4d38"),
             (6200, "#5c4b3c"), (8500, "#5a4a40"), (11200, "#574a47"), (14400, "#6a6260")],
}
WATER_RAMP = {
    "light": [(0, "#d7e9f1"), (300, "#c3dcea"), (1600, "#a9c9de"), (4900, "#8bb0cb"), (9800, "#6f94b4"),
              (16400, "#58799b"), (26200, "#46637f")],
    "dark": [(0, "#26414f"), (300, "#223b49"), (1600, "#1d3340"), (4900, "#182b37"), (9800, "#142330"),
             (16400, "#101d28"), (26200, "#0c1620")],
}

# --- Estimation --------------------------------------------------------------
# Terrain-aware surface = local (geographically weighted) quasi-binomial regression of the station
# frequency on elevation, fitted on a coarse node lattice and bicubic-upsampled, with the elevation term
# re-applied from the 1 km DEM. There is deliberately NO residual/"honour the stations" step: each station
# is a 30-year frequency (steps of ~3 %), so at the low end one station reading 0 % or 7 % is mostly sampling
# noise, and any kernel that pulls the surface toward it draws a round patch around it (the circles).
# A smoothing fit (like ANUSPLIN / PRISM's weighted regressions) averages that noise out instead.
TERRAIN_K = 24                         # neighbours used when no cross-validation is run
TERRAIN_K_CANDIDATES = (12, 16, 24, 32, 48)   # >= 12: fewer neighbours chase single noisy stations   # build() keeps the K with the lowest leave-one-out error
STATION_YEARS_EFF = 30.0               # a station frequency is ~ k / 30 (1991-2020); used as binomial n
FREQ_PSEUDO = 0.1                      # added to the success and failure counts so 0 % / 100 % stay finite
NODE_SPACING_M = 8000.0                # coarse lattice for the regression (surface is bicubic-upsampled)
RIDGE_M = 100.0                        # shrinks the elevation slope toward 0 where stations barely differ in height
SLOPE_MAX = 0.01                       # max logit units per metre of elevation
EXTRAPOLATE_MARGIN_M = 300.0
LOGIT_LIMIT = 12.0
IRLS_ITERS = 6
# Plain IDW baseline (used when no DEM is available, and as the CV benchmark).
IDW_K = 16
IDW_POWER = 2.0
IDW_EPS_M = 5000.0

# Vector line detail (metres of allowed deviation in the map projection; Natural Earth 1:10m source).
STATE_LINE_EPS_M = 100.0
CONTEXT_LINE_EPS_M = 400.0

# Map images are served as a tile pyramid on NOAA's tile grid (this many pixels per tile edge).
WEB_TILE_PX = 512

# --- Cartographic finishing ---------------------------------------------------
OVERLAY_SCALE = 2                      # overlay PNG pixels per grid cell (class edges drawn from a bicubic upsample)
MIN_REGION_KM2 = 150.0                 # smaller flat-terrain colour patches are merged into the surrounding class
SIEVE_RELIEF_M = 120.0                 # ...but not where the DEM varies by more than this over ~5 km (real summits)

# Plain-language likelihood shown in the hover card: (highest percent included, label). Same wording and edges as
# NOAA's White Christmas map (very unlikely = 10 % or less; unlikely = 11-50 %; likely = 51-90 %; very likely = above 90 %).
LIKELIHOOD = [(10, "Very Unlikely"), (50, "Unlikely"), (90, "Likely"), (100, "Very Likely")]

# --- Legend (8 classes) ----------------------------------------------------------
# NOAA's White Christmas map uses 0-10, 11-25, 26-40, 41-50, 51-60, 61-75, 76-90, 91-100 %. Thanksgiving snow
# cover is much rarer (about 2 in 3 stations are at 10 % or less, almost none above 75 %), so those classes would
# paint most of the country one colour. These breaks spread the same eight colours over the Thanksgiving range:
# 0-5, 6-10, 11-20, 21-30, 31-40, 41-50, 51-70, 71-100 %. Edit CLASS_UPPER_EDGES to change them.
CLASS_UPPER_EDGES = [5, 10, 20, 30, 40, 50, 70]           # a class includes its upper edge
# NOAA's colour ramp (grey -> dark blue -> white), sampled from NOAA's legend. The two darkest classes are
# lightened from NOAA's #3b3b3b / #304469 (they read as near-black on screen).
NOAA_COLORS = ["#6b6b6b", "#3d5a8c", "#1e50a9", "#1d71d4", "#4799e5", "#80b7ed", "#d0e5f8", "#ffffff"]
assert len(CLASS_UPPER_EDGES) + 1 == len(NOAA_COLORS)

# Headline tiles on the page: share of land area with a chance of at least KPI_HIGH_PCT / at most KPI_LOW_PCT.
KPI_HIGH_PCT = 25
KPI_LOW_PCT = 10


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def parse_day(text: str) -> tuple[int, int]:
    """'11-26' (or '11/26') -> (11, 26)."""
    try:
        m, d = (int(x) for x in text.replace("/", "-").split("-"))
    except ValueError:
        raise ValueError(f"date must look like MM-DD, got {text!r}") from None
    if not (1 <= m <= 12 and 1 <= d <= 31):
        raise ValueError(f"not a calendar date: {text!r}")
    return m, d


def date_label(days: list[tuple[int, int]]) -> str:
    """[(11, 26)] -> 'Nov 26';  Nov 22..28 -> 'Nov 22\u201328'."""
    days = sorted(days)
    (m0, d0), (m1, d1) = days[0], days[-1]
    if len(days) == 1:
        return f"{_MONTHS[m0 - 1]} {d0}"
    return f"{_MONTHS[m0 - 1]} {d0}\u2013{d1}" if m0 == m1 else f"{_MONTHS[m0 - 1]} {d0} \u2013 {_MONTHS[m1 - 1]} {d1}"


def class_labels() -> list[str]:
    e = CLASS_UPPER_EDGES
    lo = [0] + [x + 1 for x in e]
    hi = e + [100]
    return [f"{a}\u2013{b}%" for a, b in zip(lo, hi)]


def class_index(p: float) -> int:
    """0..7. 10 -> class 0, 10.5 -> class 1, 25 -> class 1, 91 -> class 7."""
    return sum(p > e for e in CLASS_UPPER_EDGES)
