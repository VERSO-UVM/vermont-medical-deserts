# Vermont medical deserts

An interactive map of health care provider access in Vermont, comparing where providers practice with drive times over the road network.

**Live map:** https://verso-uvm.github.io/vermont-medical-deserts/

## What it shows

- Every active provider with a Vermont practice address in the CMS NPPES file (November 2026), grouped into categories such as primary care, mental health, dental and pharmacy.
- For each 1.5 km grid square, the drive time to the nearest provider in the selected category.
- How many provider locations are within 10, 15, 20, 30 or 45 minutes ("overlap"), and which areas are beyond the selected threshold ("holes").
- The towns with the most area beyond the threshold.

## Data sources

- Providers: [CMS NPPES monthly file](https://download.cms.gov/nppes/NPI_Files.html). Active NPIs whose practice address is in Vermont.
- Geocoding: [US Census Geocoder](https://geocoding.geo.census.gov/). About 93% of providers matched a street address. The rest are placed at their ZIP code's centroid and appear as hollow dots.
- Roads: [OpenStreetMap](https://www.openstreetmap.org/copyright) Vermont extract from Geofabrik.
- Town boundaries: Vermont Center for Geographic Information (VCGI).

## Limitations

- Drive times use typical speeds for each road class, and treat unpaved roads as slower. They don't account for traffic, weather or seasonal road closures.
- Only Vermont roads and providers are included. Border areas may have closer care in New Hampshire, New York, Massachusetts or Québec.
- NPPES practice addresses are self-reported and sometimes point to a billing office rather than the place where patients are seen.
- Coverage is measured by land area, not by population.

## Rebuilding the data

The map is static: `index.html` loads `data.js` (providers, grid and towns) and `roads.js` (drive times). The scripts in `scripts/` rebuild those two files. Run them from a working folder that contains `work/` and `app/` subfolders:

1. `python scripts/vt_npi_extract.py NPPES_Data_Dissemination_<Month>_<Year>.zip` writes `vt_npi.csv`.
2. `python scripts/geocode.py` geocodes addresses into `work/geocoded.json`.
3. Download the following into `work/`:
   - the Census 2024 ZCTA gazetteer, saved as `zcta.zip`
   - VCGI town boundaries, saved as `vt_towns.geojson`
   - the Geofabrik Vermont extract, saved as `osm/vermont-latest.osm.pbf`
4. `python scripts/build.py` writes `app/data.js`.
5. `python scripts/roads.py` writes `app/roads.js`. It needs `numpy`, `scipy` and `osmium`.

Copy `app/data.js` and `app/roads.js` to the repo root to publish.
