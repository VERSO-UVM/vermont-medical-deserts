"""Read 2020 Census DHC block data (population, under 18, 65+, age sum) from a state's summary-file ZIP.

Files: https://www2.census.gov/programs-surveys/decennial/2020/data/demographic-and-housing-characteristics-file/<State>/
"""
import io, zipfile
import numpy as np

GEO = {'sumlev': 2, 'geocomp': 3, 'logrecno': 7, 'pop': 90, 'lat': 92, 'lon': 93}   # 0-based geo-header fields
P12 = 5 + 71 + 73                      # segment 6: 5 id fields, then P10 (71), P11 (73), P12 (sex by age)
UNDER18 = [3, 4, 5, 6, 27, 28, 29, 30]
OVER65 = list(range(20, 26)) + list(range(44, 50))
# P12 age brackets (male 003-025, female 027-049) and their mid-points in years; 85+ is open-ended -> 89
MIDS = [2.5, 7.5, 12.5, 16.5, 19, 20.5, 21.5, 23.5, 27.5, 32.5, 37.5, 42.5, 47.5, 52.5, 57.5,
        61, 63.5, 66, 68.5, 72.5, 77.5, 82.5, 89]


def read_blocks(zip_path, st):
    """Rows of [lat, lon, population, under 18, 65+, sum of ages] for every populated block."""
    z = zipfile.ZipFile(zip_path)
    st = st.lower()
    blocks = {}
    for line in io.TextIOWrapper(z.open(f'{st}geo2020.dhc'), encoding='latin-1'):
        f = line.rstrip('\n').split('|')
        if f[GEO['sumlev']] == '100' and f[GEO['geocomp']] == '00' and int(f[GEO['pop']]):
            blocks[f[GEO['logrecno']]] = [float(f[GEO['lat']]), float(f[GEO['lon']])]
    rows = []
    for line in io.TextIOWrapper(z.open(f'{st}000062020.dhc'), encoding='latin-1'):
        f = line.split('|')
        if f[4] in blocks:
            p = lambda k: int(f[P12 + k - 1])
            agesum = sum(m * (p(3 + j) + p(27 + j)) for j, m in enumerate(MIDS))
            rows.append(blocks[f[4]] + [p(1), sum(map(p, UNDER18)), sum(map(p, OVER65)), agesum])
    return np.array(rows)
