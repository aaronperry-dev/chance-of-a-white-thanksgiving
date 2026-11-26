# Probability of a White Thanksgiving — CONUS dashboard

A static dashboard for GitHub Pages: the historical probability of **at least 1 inch of snow on the ground on Thanksgiving Day** (1991–2020 U.S. Climate Normals, NOAA NCEI) over the contiguous U.S., drawn in NOAA's map style. It is the Thanksgiving version of the "Chance of a White Christmas" dashboard.

## What changed from the White Christmas version

* **Data source.** NOAA's White Christmas map is a single-date product (Dec 25). Thanksgiving has no NOAA map, so the stations now come from NCEI's **daily** 1991–2020 Climate Normals, element `DLY-SNWD-PCTALL-GE001WI` (probability that snow depth is ≥ 1 inch), which exists for every calendar day. It is the same quantity NOAA maps for Dec 25 (the Dec 25 value for Leoti, KS is 16.5 % in both). About 4,300 CONUS stations have at least 10 years of record and a value.
* **Which date.** Thanksgiving is the 4th Thursday of November, so it falls on Nov 22–28. By default the map shows the **mean of those seven dates** (they differ by about 1 point at the median station and by up to ~13 points at the most sensitive high-elevation ones). To map a single date instead, run `python build.py --date 11-26` (Thanksgiving 2026 is Nov 26), or edit `THANKSGIVING_DAYS` in `config.py`.
* **Legend classes.** Thanksgiving snow cover is much rarer than Christmas (about 2 in 3 stations are at 10 % or less, almost none above 75 %), so NOAA's Christmas breaks would paint most of the country one colour. The same eight colours now cover 0–5, 6–10, 11–20, 21–30, 31–40, 41–50, 51–70 and 71–100 % (`CLASS_UPPER_EDGES` in `config.py`). The hover-card wording (Very Unlikely ≤ 10 %, Unlikely 11–50 %, Likely 51–90 %, Very Likely > 90 %) is unchanged.
* **Headline tiles.** Share of land area with a chance of **25 % or better** and **10 % or lower** (`KPI_HIGH_PCT`, `KPI_LOW_PCT`); at Thanksgiving a 50 % tile would be almost empty.
* **No NOAA reference-tile switch.** That layer is NOAA's Dec 25 map, which does not apply here, so it was removed.
* **Flat repository.** Everything sits in the top folder (only `.github/workflows/` is a folder, because GitHub requires it). The Python modules that used to be in `pipeline/` are now top-level files, the web page and its bundled libraries are top-level files, and the workflow assembles the published site (`_site/`) from just the web files.

## How the map is made

**Why the surface is generated here.** NOAA publishes station values but no raw grid, so the build estimates the surface from the station values on a clean 1 km grid in NOAA's projection, shaped by terrain.

* **Surface:** a 1 km grid in **ESRI:102009** (North America Lambert Conformal Conic), the projection of NOAA's web app, drawn by Leaflet in NOAA's tile-grid zoom levels. Estimator: a *geographically weighted quasi-binomial regression* of the station frequency on elevation (the K nearest stations, tricube weights; slope constrained to "higher = snowier" and shrunk where the stations barely differ in height). It is solved on an 8 km node lattice, the fitted level and slope are bicubic-upsampled, and the elevation term is applied from the 1 km terrain grid, so the field is smooth regionally and follows the terrain locally. K (12–48) is picked by leave-one-out error at the stations. It **smooths** the stations instead of honouring them: each station is a ~30-year frequency, so at the low end one 0 % or 7 % reading is mostly sampling noise, and pulling the surface toward it would draw a round patch around it. Elevation comes from AWS Open Data **Terrain Tiles** (Terrarium PNG, zoom 7, ≈1 km). The build runs a leave-one-out check against plain inverse-distance weighting; if terrain does not win, it uses the plain version.
* **Cartographic finishing:** the overlay PNG is drawn at 2x the grid. Class edges are cut from a bicubic upsample of the smooth surface, then colour patches smaller than `MIN_REGION_KM2` (150 km²) in flat terrain are merged into the surrounding class; patches on real relief (more than `SIEVE_RELIEF_M`, 120 m, of height change over about 3 miles) are kept, so mountain tops stay. The hover value and station table use the unsieved surface.
* **Tile pyramid:** the overlay, hillshade and base maps are cut into 512 px tiles on NOAA's tile grid (`tiles.py`, `data/tiles/`), so the browser loads and draws only what is on screen. `--keep-sources` also keeps the whole-image files.
* **Land and water base map:** under the surface, a colour map of land elevation and ocean / lake depth (light and dark versions). Cells with a chance of **1 % or less** are left transparent so this map shows through (`TRANSPARENT_AT_OR_BELOW_PCT` in `config.py`). Lakes and country shapes are Natural Earth. The base map is optional: if its Natural Earth files cannot be downloaded (or with `--no-base`), the page falls back to a flat grey background.
* **Terrain relief:** a hillshade of that elevation, drawn as a translucent black/white layer, with a toolbar switch and strength slider.
* **Hover card / click look-up:** the estimated chance at that spot with a plain-language label, plus the nearest station (name, distance, its own value). The page downloads a one-byte-per-cell value grid so a click reports the exact modelled value of that cell.
* **Stations:** dots (toolbar or on-map switch), search, and a "Stations by chance" table that recalculates for the part of the map in view. The headline tiles are shares of **land area** from the surface.
* **Units:** everything the page shows is imperial (percent, inches, feet, miles). Internally the pipeline works in metres.
* **Light / Dark toggle, Wide map, state lines (on), place labels (off).** Coastlines, borders and the land mask come from Natural Earth 1:10m.

## Files

```
index.html  app.js  style.css       the page
leaflet.js  leaflet.css             bundled map libraries (see THIRD_PARTY_LICENSES.txt)
proj4.js  proj4leaflet.js
build.py                            entry point: stations + terrain -> data/
config.py                           every setting: dates, sources, classes, colours, estimation
stations.py                         NCEI daily normals -> station table
fetch.py dem.py boundary.py geo.py grid.py interp.py cartography.py render.py tiles.py basemap.py webvec.py demo.py
test_pipeline.py  test_surface.py   pytest, synthetic fixtures only, no network
.github/workflows/pages.yml         build + deploy to GitHub Pages
data/   (generated)  cache/ (downloaded inputs)  _site/ (what the Action publishes)   -- all git-ignored
```

## Deploy to GitHub Pages

1. Create a repo (default branch `main`) and upload everything in this folder, **including the `.github/workflows/pages.yml` file** (folders starting with a dot are hidden on macOS and can be skipped by drag-and-drop; if so, use *Add file → Create new file* on GitHub, name it `.github/workflows/pages.yml` and paste the contents).
2. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
3. Push, or run the workflow from the **Actions** tab. It runs the tests, builds `data/`, and publishes the web files.

The page will be at `https://<user>.github.io/<repo>/`. NOAA's inputs change only when new Normals are issued (next ~2031), so there is no schedule. A cold build streams the 300 MB NCEI archive once (a minute or two), downloads about a thousand terrain tiles and takes a few minutes in total; the distilled station file, terrain tiles and boundaries are cached between runs, and the 300 MB archive itself is not kept.

## Run locally

```bash
pip install -r requirements.txt
python -m pytest -q
python build.py                      # downloads stations + terrain, writes data/
python -m http.server 8000           # open http://localhost:8000
```

Flags: `--date MM-DD` (one date instead of the Nov 22–28 mean), `--archive FILE` (use a local copy of NCEI's by-station `.tar.gz`), `--refresh` (re-read the normals), `--res METRES` (grid size, default 1000), `--dem-zoom 7|8` (terrain detail; 8 is ~2x finer and 4x the download), `--no-terrain` (plain interpolation, no relief or base map), `--no-base`, `--no-overlays`, `--keep-sources`, `--demo` (**synthetic** stations and terrain for previewing; the page shows a "DEMO DATA" banner).

### If a download is blocked

* NCEI archive unreachable → download `us-climate-normals_1991-2020_v1.0.1_daily_multivariate_by-station_*.tar.gz` from <https://www.ncei.noaa.gov/data/normals-daily/1991-2020/archive/> and run `python build.py --archive path/to/file.tar.gz`. A hand-placed distilled `cache/stations_1122-1128.json` is also used without touching the network.
* The state boundaries (Natural Earth, about 40 MB) are required: they define the land the surface covers. Hand-place `ne_10m_admin_1_states_provinces.geojson` in `cache/` if a runner cannot download it. The state-line / place-label / Canada-Mexico overlays are optional and skipped if their downloads fail.
* AWS terrain tiles unreachable → the build stops with the tile that failed. `--no-terrain` builds the plain interpolated surface without relief.

## Caveats

* The surface is a **model**, not NOAA's grid: it follows NOAA's station values, but between stations (mountains especially) it can differ from what a gridded product would show. The build prints the leave-one-out error, and the page footer shows it.
* A click reports the modelled value for that 1 km cell and the nearest station's measured value; neither is a forecast. Climatology is not a forecast.
* Station values are 1991–2020 normals of daily snow-depth statistics; a station's own value for a single date can move by a point or two from day to day, which is why the default is the seven-date mean.

## Credits

NOAA National Centers for Environmental Information (NCEI), 1991–2020 U.S. Climate Normals · Map style after NOAA Climate.gov's White Christmas map · Elevation: AWS Open Data Terrain Tiles (Mapzen / SRTM, NED and other sources) · Leaflet (BSD-2-Clause), Proj4Leaflet (BSD-2-Clause), proj4js (MIT) · Natural Earth (public domain).
