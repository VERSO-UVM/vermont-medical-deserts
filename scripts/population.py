"""Attach 2020 Census block population (total, under 18, 65+) to the map grid.

Reads the Vermont 2020 DHC summary file (work/census/vt2020.dhc.zip from
https://www2.census.gov/programs-surveys/decennial/2020/data/demographic-and-housing-characteristics-file/Vermont/)
and app/data.js; writes app/pop.js. Each block is assigned to the grid cell
nearest its internal point. Run with the project venv.
"""
import base64, io, json, zipfile
import numpy as np
from scipy.spatial import cKDTree

GEO = {'sumlev': 2, 'geocomp': 3, 'logrecno': 7, 'pop': 90, 'lat': 92, 'lon': 93}   # 0-based
P12 = 5 + 71 + 73                      # segment 6: 5 id fields, then P10 (71), P11 (73), P12
UNDER18 = [3, 4, 5, 6, 27, 28, 29, 30]
OVER65 = list(range(20, 26)) + list(range(44, 50))
# P12 age brackets (same order for male 003-025 and female 027-049) and their mid-points in years;
# 85+ is open-ended, so 89 is used. Mean age per cell = sum(count * mid-point) / population.
MIDS = [2.5, 7.5, 12.5, 16.5, 19, 20.5, 21.5, 23.5, 27.5, 32.5, 37.5, 42.5, 47.5, 52.5, 57.5,
        61, 63.5, 66, 68.5, 72.5, 77.5, 82.5, 89]
MIN_POP_FOR_AGE = 10

z = zipfile.ZipFile('work/census/vt2020.dhc.zip')
blocks = {}
for line in io.TextIOWrapper(z.open('vtgeo2020.dhc'), encoding='latin-1'):
    f = line.rstrip('\n').split('|')
    if f[GEO['sumlev']] == '100' and f[GEO['geocomp']] == '00' and int(f[GEO['pop']]):
        blocks[f[GEO['logrecno']]] = [float(f[GEO['lat']]), float(f[GEO['lon']])]

rows = []
for line in io.TextIOWrapper(z.open('vt000062020.dhc'), encoding='latin-1'):
    f = line.split('|')
    if f[4] in blocks:
        p = lambda k: int(f[P12 + k - 1])
        agesum = sum(m * (p(3 + j) + p(27 + j)) for j, m in enumerate(MIDS))
        rows.append(blocks[f[4]] + [p(1), sum(map(p, UNDER18)), sum(map(p, OVER65)), agesum])
rows = np.array(rows)
print('blocks with people', len(rows), 'total', rows[:, 2:5].sum(0).astype(int),
      'statewide mean age %.1f' % (rows[:, 5].sum() / rows[:, 2].sum()))

src = open('app/data.js', encoding='utf-8').read()
g = json.loads(src.split('window.DATA=')[1].split(';\nwindow.TOWNS')[0])['grid']
cells = np.array(g['cells']) + [g['dlat'] / 2, g['dlon'] / 2]
kx = np.cos(np.radians(43.9))
_, idx = cKDTree(np.c_[cells[:, 0], cells[:, 1] * kx]).query(np.c_[rows[:, 0], rows[:, 1] * kx])

out = {}
for name, col in (('all', 2), ('u18', 3), ('o65', 4)):
    a = np.bincount(idx, weights=rows[:, col], minlength=len(cells)).round()
    assert a.max() < 65536
    out[name] = base64.b64encode(a.astype(np.uint16).tobytes()).decode()
    print(name, 'max per cell %d' % a.max(), 'sum %d' % a.sum())

# mean age x10 per cell (0 = too few residents to say)
pop = np.bincount(idx, weights=rows[:, 2], minlength=len(cells))
agesum = np.bincount(idx, weights=rows[:, 5], minlength=len(cells))
mean10 = np.where(pop >= MIN_POP_FOR_AGE, np.round(10 * agesum / np.maximum(pop, 1)), 0).astype(np.uint16)
out['age10'] = base64.b64encode(mean10.tobytes()).decode()
shown = mean10 > 0
print('mean age: cells shown %d of %d, people covered %.1f%%, cell range %.1f-%.1f' % (
    shown.sum(), len(cells), 100 * pop[shown].sum() / pop.sum(), mean10[shown].min() / 10, mean10.max() / 10))
with open('app/pop.js', 'w', encoding='utf-8') as f:
    f.write('window.POP=' + json.dumps(out) + ';\n')
