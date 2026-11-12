"""Attach 2020 Census block population (total, under 18, 65+, mean age) to the Vermont map grid.

Reads work/census/vt2020.dhc.zip and app/data.js; writes app/pop.js. Each block is assigned to the
grid cell nearest its internal point. Run with the project venv.
"""
import base64, json, os, sys
import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # shared modules live beside this script
from census import read_blocks  # noqa: E402

MIN_POP_FOR_AGE = 10                   # mean age is only shown for cells with at least this many residents

rows = read_blocks('work/census/vt2020.dhc.zip', 'VT')
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
with open('app/pop.js', 'w', encoding='utf-8') as f:
    f.write('window.POP=' + json.dumps(out) + ';\n')
