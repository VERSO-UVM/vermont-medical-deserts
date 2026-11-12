"""Drive-time access over the OSM road network.

Reads work/osm/vermont-latest.osm.pbf and app/data.js (built by build.py) and
writes app/roads.js with, for every grid cell and every category/filter combo:
  - minutes to the nearest provider location by road
  - number of provider locations reachable within each threshold
Run with the project venv:  .venv/Scripts/python roads.py
"""
import base64, json, os, sys, time
import numpy as np
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # shared modules live beside this script
from roadnet import build, Snapper  # noqa: E402

THRESHOLDS = [10, 15, 20, 30, 45]          # minutes
LIMIT = max(THRESHOLDS) + 15                # search cutoff; beyond this we store 255

t0 = time.time()
lat, lon, G = build(['work/osm/vermont-latest.osm.pbf'])
snap = Snapper(lat, lon, G).snap

src = open('app/data.js', encoding='utf-8').read()
D = json.loads(src.split('window.DATA=')[1].split(';\nwindow.TOWNS')[0])
g = D['grid']
cells = np.array([[c[0] + g['dlat'] / 2, c[1] + g['dlon'] / 2] for c in g['cells']])
cnode, coff = snap(cells)
print('cells', len(cells))

cats = ['all'] + [c[0] for c in D['cats']]
filters = ['all', 'org', 'ind', 'mcr']     # mcr = individuals who billed Medicare Part B in 2024
combo = {(c, f): i for i, (c, f) in enumerate((c, f) for c in cats for f in filters)}
NC = len(combo)

# group provider locations by snapped road node
lnode, loff = snap([l['ll'] for l in D['locs']])
by_node = {}
for k, l in enumerate(D['locs']):
    s = by_node.setdefault(int(lnode[k]), {'off': [], 'combos': []})
    keys = set()
    for p in l['p']:
        f = 'org' if p[3] == 2 else 'ind'
        for c in ((p[1],) if p[1] == 'sn' else ('all', p[1])):   # safety-net sites are not NPPES rows
            keys |= {(c, 'all'), (c, f)}
            if f == 'ind' and p[4] > 0:
                keys.add((c, 'mcr'))
    s['off'].append(loff[k]); s['combos'].append([combo[x] for x in keys])

nearest = np.full((NC, len(cells)), 255.0)
counts = np.zeros((NC, len(THRESHOLDS), len(cells)), dtype=np.int32)
srcs = list(by_node)
print('source nodes', len(srcs))
for b in range(0, len(srcs), 64):
    batch = srcs[b:b + 64]
    dist = dijkstra(G, indices=batch, limit=LIMIT)[:, cnode] + coff     # (batch, cells)
    for r, s in enumerate(batch):
        for off, cl in zip(by_node[s]['off'], by_node[s]['combos']):
            m = dist[r] + off
            within = np.stack([m <= t for t in THRESHOLDS])
            for ci in cl:
                np.minimum(nearest[ci], m, out=nearest[ci])
                counts[ci] += within
    if b % 640 == 0:
        print('  %d/%d sources  %.0fs' % (b + len(batch), len(srcs), time.time() - t0), flush=True)

b64 = lambda a: base64.b64encode(np.clip(np.rint(a), 0, 255).astype(np.uint8).tobytes()).decode()
out = {'thresholds': THRESHOLDS, 'combos': [f'{c}|{f}' for (c, f) in combo],
       'nearest': [b64(nearest[i]) for i in range(NC)],
       'counts': [[b64(counts[i, j]) for j in range(len(THRESHOLDS))] for i in range(NC)]}
with open('app/roads.js', 'w', encoding='utf-8') as f:
    f.write('window.ROADS=' + json.dumps(out, separators=(',', ':')) + ';\n')
pc = nearest[combo[('pc', 'all')]]
print('done %.0fs' % (time.time() - t0),
      '| primary care: cells >20 min %.1f%%, >30 min %.1f%%' % (100 * (pc > 20).mean(), 100 * (pc > 30).mean()))
