# Vermont medical deserts

An interactive map of health care access in Vermont. It shows where providers practice, how long the drive is over the real road network, and how many people live beyond a chosen drive time.

**Live map:** https://verso-uvm.github.io/vermont-medical-deserts/

## What it shows

- **Providers:** every active provider with a Vermont practice address in the CMS NPPES file (November 2026), grouped into categories such as primary care, mental health, dental and pharmacy.
- **Safety-net clinics:** federally qualified health center (FQHC) sites and rural health clinics (RHCs). These can be used as their own category for drive times, or shown as an overlay.
- **Drive time:** for each 1.5 km grid square, the drive time to the nearest provider in the selected category.
- **Overlap:** how many provider locations are within 10, 15, 20, 30 or 45 minutes.
- **Holes:** the areas beyond the selected threshold.
- **People beyond the threshold:** counts for all residents, people 65+, children under 18 and households without a vehicle.
- **Billed Medicare filter:** an optional filter that keeps only clinicians with 2024 Medicare Part B claims. It screens out registrations that don't appear to be in active practice. It's only offered for primary care, specialists and nursing/NP/PA, where Medicare data is meaningful.
- **Shortage areas:** federal Health Professional Shortage Areas (HPSAs) for primary care, dental and mental health, as an overlay.
- **Towns:** the towns with the most people beyond the threshold.

## Data sources

| Data | Source |
|---|---|
| Providers | [CMS NPPES monthly file](https://download.cms.gov/nppes/NPI_Files.html) |
| Geocoding | [US Census Geocoder](https://geocoding.geo.census.gov/). About 93% of providers matched a street address; the rest sit at a ZIP centroid (hollow dots). |
| Roads | [OpenStreetMap](https://www.openstreetmap.org/copyright) Vermont extract from Geofabrik |
| Town boundaries | Vermont Center for Geographic Information (VCGI) |
| Population and age | [2020 Census DHC](https://www2.census.gov/programs-surveys/decennial/2020/data/demographic-and-housing-characteristics-file/Vermont/), table P12, census blocks |
| Households without a vehicle | [ACS 2020–2024 5-year](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/), table B25044, block groups. Spread over each block group's blocks by population. |
| Medicare activity | [Medicare Physician & Other Practitioners – by Provider, 2024](https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider) |
| Health center sites | [HRSA Health Center Service Delivery Sites](https://data.hrsa.gov/data/download) |
| Rural health clinics | [CMS Rural Health Clinic Enrollments](https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/rural-health-clinic-enrollments) |
| Shortage areas | [HRSA HPSA component boundaries](https://data.hrsa.gov/data/download). Includes areas that are designated or proposed for withdrawal. |

## Limitations

- **Drive times** use typical speeds for each road class, and treat unpaved roads as slower. They don't account for traffic, weather or seasonal road closures.
- **Borders:** only Vermont roads and providers are included. Border towns such as Stamford, Lunenburg and Readsboro rank worse than residents likely experience, because closer care in New Hampshire, New York or Massachusetts isn't counted.
- **Addresses:** NPPES practice addresses are self-reported and sometimes point to a billing office rather than the place where patients are seen.
- **Medicare filter:** clinicians at health centers, rural health clinics and hospital outpatient departments usually bill through the facility, so the "Billed Medicare" filter leaves them out.
- **Population** is from 2020 while providers are from 2026. Small census blocks include Census privacy noise, but town and state totals are reliable.
- **Mental health shortage areas:** Vermont has no area-based mental health HPSAs. Its only mental health designations are attached to individual health centers.

## Files

The site is static. `index.html` loads `style.css`, Leaflet (pinned with an integrity hash), the data files and `app.js`. A Content-Security-Policy limits the page to its own files, unpkg.com (for Leaflet) and OpenStreetMap tiles.

| File | Contents |
|---|---|
| `data.js` | Providers, safety-net sites, grid and town boundaries |
| `roads.js` | Drive times and overlap counts per grid square |
| `pop.js` | Population per grid square |
| `hpsa.js` | Shortage-area boundaries |

## Rebuilding the data

The scripts in `scripts/` rebuild the data files. Install the dependencies with `pip install -r scripts/requirements.txt`. Then, from a working folder that contains `work/` and `app/`:

1. `python scripts/vt_npi_extract.py NPPES_Data_Dissemination_<Month>_<Year>.zip` writes `vt_npi.csv`.
2. `python scripts/geocode.py` geocodes addresses into `work/geocoded.json`.
3. Download the following into `work/`:
   - `zcta.zip`: the Census 2024 ZCTA gazetteer
   - `vt_towns.geojson`: VCGI town boundaries
   - `osm/vermont-latest.osm.pbf`: the Geofabrik extract
   - `medicare/vt_0.json`: Medicare by-provider records for Vermont
   - the HRSA files, in `hrsa/`
   - `rhc_vt.json` and `rhc_geo.json`: rural health clinics and their geocodes
   - `census/vt2020.dhc.zip`
   - `acs/b25044.dat`
4. `python scripts/build.py` writes `app/data.js`.
5. `python scripts/roads.py` writes `app/roads.js`.
6. `python scripts/population.py` writes `app/pop.js`.
7. `python scripts/hpsa.py` writes `app/hpsa.js`.

Copy the files in `app/` to the repo root to publish.
