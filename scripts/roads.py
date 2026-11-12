"""Drive-time access over the OSM road network.

Reads work/osm/vermont-latest.osm.pbf and app/data.js (built by build.py) and
writes app/roads.js with, for every grid cell and every category/filter combo:
  - minutes to the nearest provider location by road
  - number of provider locations reachable within each threshold
Run with the project venv:  .venv/Scripts/python roads.py
"""
import base64, json, math, time
import numpy as np
import osmium
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra, connected_components
from scipy.spatial import cKDTree

THRESHOLDS = [10, 15, 20, 30, 45]          # minutes
LIMIT = max(THRESHOLDS) + 15                # search cutoff; beyond this we store 255
OFFROAD_KMH = 16                            # cost of getting from a cell/address to the road
NODE_SPACING_M = 400                        # keep a routing node at least this often along a road

KMH = {'motorway': 105, 'motorway_link': 60, 'trunk': 90, 'trunk_link': 50,
       'primary': 80, 'primary_link': 45, 'secondary': 70, 'secondary_link': 40,
       'tertiary': 60, 'tertiary_link': 35, 'unclassified': 50, 'residential': 40,
       'living_street': 15, 'service': 20, 'road': 40}
UNPAVED = {'unpaved', 'gravel', 'dirt', 'ground', 'compacted', 'fine_gravel', 'earth', 'sand', 'grass'}


def hav_m(lat1, lon1, lat2, lon2):
    r = math.pi / 180
    h = (math.sin((lat2 - lat1) * r / 2) ** 2 +
         math.cos(lat1 * r) * math.cos(lat2 * r) * math.sin((lon2 - lon1) * r / 2) ** 2)
    return 12742000 * math.asin(math.sqrt(h))


def speed(tags):
    hw = tags.get('highway')
    if hw not in KMH:
        return None
    if tags.get('access') in ('private', 'no') or tags.get('motor_vehicle') in ('private', 'no'):
        return None
    if hw == 'service' and tags.get('service') in ('parking_aisle', 'driveway', 'drive-through'):
        return None
    if tags.get('area') == 'yes':
        return None
    v = KMH[hw]
    ms = tags.get('maxspeed', '')
    try:
        n = float(ms.split()[0])
        v = min(v, n * (1.609 if 'mph' in ms or n <= 70 else 1) * 0.9)
    except (ValueError, IndexError):
        pass
    if tags.get('surface') in UNPAVED:
        v *= 0.75
    return v


class Ways(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []          # (kmh, [(node_id, lat, lon), ...])

    def way(self, w):
        v = speed(w.tags)
        if v is None:
            return
        try:
            pts = [(n.ref, n.location.lat, n.location.lon) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if len(pts) > 1:
            self.ways.append((v, pts))


t0 = time.time()
h = Ways()
h.apply_file('work/osm/vermont-latest.osm.pbf', locations=True)
print('ways', len(h.ways), '%.0fs' % (time.time() - t0))

# nodes shared by several ways (intersections) must stay; others are thinned
use = {}
for _, pts in h.ways:
    for i, (nid, _, _) in enumerate(pts):
        use[nid] = use.get(nid, 0) + (2 if i in (0, len(pts) - 1) else 1)

ids, lat, lon, A, B, W = {}, [], [], [], [], []


def nid_index(nid, la, lo):
    if nid not in ids:
        ids[nid] = len(lat); lat.append(la); lon.append(lo)
    return ids[nid]


for v, pts in h.ways:
    prev = nid_index(*pts[0]); acc = 0.0
    for i in range(1, len(pts)):
        acc += hav_m(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2])
        last = i == len(pts) - 1
        if last or use[pts[i][0]] > 1 or acc >= NODE_SPACING_M:
            cur = nid_index(*pts[i])
            if cur != prev:
                A.append(prev); B.append(cur); W.append(acc / 1000 / v * 60)   # minutes
            prev, acc = cur, 0.0

lat, lon = np.array(lat), np.array(lon)
n = len(lat)
G = coo_matrix((W + W, (A + B, B + A)), shape=(n, n)).tocsr()   # treated as two-way
ncomp, lab = connected_components(G, directed=False)
main = lab == np.bincount(lab).argmax()
print('routing nodes', n, 'edges', len(A), 'main component', main.sum(), '%.0fs' % (time.time() - t0))

# snap points to the nearest node of the main component (local km projection)
KX = 111.32 * math.cos(math.radians(43.9))
mi = np.nonzero(main)[0]
tree = cKDTree(np.c_[lon[mi] * KX, lat[mi] * 111.32])


def snap(pts):
    p = np.asarray(pts)
    d, j = tree.query(np.c_[p[:, 1] * KX, p[:, 0] * 111.32])
    return mi[j], d / OFFROAD_KMH * 60      # node index, minutes off-road

src = open('app/data.js', encoding='utf-8').read()
D = json.loads(src.split('window.DATA=')[1].split(';\nwindow.TOWNS')[0])
g = D['grid']
cells = np.array([[c[0] + g['dlat'] / 2, c[1] + g['dlon'] / 2] for c in g['cells']])
cnode, coff = snap(cells)
print('cells', len(cells), 'median cell->road km %.2f, >3km: %d' %
      (np.median(coff) * OFFROAD_KMH / 60, (coff * OFFROAD_KMH / 60 > 3).sum()))

cats = ['all'] + [c[0] for c in D['cats']]
filters = ['all', 'org', 'ind']
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
        for c in ('all', p[1]):
            keys |= {(c, 'all'), (c, f)}
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
       'counts': [[b64(counts[i, j]) for j in range(len(THRESHOLDS))] for i in range(NC)],
       'farFromRoad': b64((coff * OFFROAD_KMH / 60 > 3).astype(np.uint8))}
with open('app/roads.js', 'w', encoding='utf-8') as f:
    f.write('window.ROADS=' + json.dumps(out, separators=(',', ':')) + ';\n')
pc = nearest[combo[('pc', 'all')]]
print('done %.0fs' % (time.time() - t0),
      '| primary care: cells >20 min %.1f%%, >30 min %.1f%%' % (100 * (pc > 20).mean(), 100 * (pc > 30).mean()))
