"""Road network from OpenStreetMap extracts, shared by the Vermont map and the regional comparison.

build(files, bbox) -> (lat, lon, G): routing nodes and a symmetric CSR matrix of travel minutes.
Snapper(...).snap(points) -> (node index, off-road minutes) for [lat, lon] points.
"""
import math, time
import numpy as np
import osmium
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

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
    """Typical km/h for a drivable way, or None if cars can't use it."""
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


class _Ways(osmium.SimpleHandler):
    def __init__(self, bbox):
        super().__init__()
        self.ways, self.bbox = [], bbox     # ways: (way_id, kmh, [(node_id, lat, lon), ...])

    def way(self, w):
        v = speed(w.tags)
        if v is None:
            return
        try:
            pts = [(n.ref, n.location.lat, n.location.lon) for n in w.nodes]
        except osmium.InvalidLocationError:
            return
        if self.bbox:
            s, wst, nth, e = self.bbox
            if not any(s <= la <= nth and wst <= lo <= e for _, la, lo in pts):
                return
        if len(pts) > 1:
            self.ways.append((w.id, v, pts))


def build(files, bbox=None):
    """bbox = (south, west, north, east). Ways shared by several files are merged by OSM id."""
    t0 = time.time()
    ways, seen = [], set()
    for f in files:
        h = _Ways(bbox)
        h.apply_file(f, locations=True)
        for wid, v, pts in h.ways:
            if wid not in seen:                  # border roads appear in both neighbouring extracts
                seen.add(wid); ways.append((v, pts))
        print('  %s: %d ways (%.0fs)' % (f.split('/')[-1], len(h.ways), time.time() - t0), flush=True)

    use = {}                                 # intersections and way ends must stay as nodes
    for _, pts in ways:
        for i, (nid, _, _) in enumerate(pts):
            use[nid] = use.get(nid, 0) + (2 if i in (0, len(pts) - 1) else 1)

    ids, lat, lon, A, B, W = {}, [], [], [], [], []

    def idx(nid, la, lo):
        if nid not in ids:
            ids[nid] = len(lat); lat.append(la); lon.append(lo)
        return ids[nid]

    for v, pts in ways:
        prev, acc = idx(*pts[0]), 0.0
        for i in range(1, len(pts)):
            acc += hav_m(pts[i - 1][1], pts[i - 1][2], pts[i][1], pts[i][2])
            if i == len(pts) - 1 or use[pts[i][0]] > 1 or acc >= NODE_SPACING_M:
                cur = idx(*pts[i])
                if cur != prev:
                    A.append(prev); B.append(cur); W.append(acc / 1000 / v * 60)   # minutes
                prev, acc = cur, 0.0
    n = len(lat)
    G = coo_matrix((W + W, (A + B, B + A)), shape=(n, n)).tocsr()   # treated as two-way
    print('  routing nodes %d, edges %d (%.0fs)' % (n, len(A), time.time() - t0), flush=True)
    return np.array(lat), np.array(lon), G


class Snapper:
    """Snap points to the nearest routing node. main_only: largest component only (one-state network);
    otherwise any component with at least min_nodes nodes (keeps islands such as Nantucket)."""

    def __init__(self, lat, lon, G, ref_lat=43.9, main_only=True, min_nodes=1000):
        _, lab = connected_components(G, directed=False)
        size = np.bincount(lab)
        ok = lab == size.argmax() if main_only else size[lab] >= min_nodes
        self.kx = 111.32 * math.cos(math.radians(ref_lat))
        self.mi = np.nonzero(ok)[0]
        self.tree = cKDTree(np.c_[lon[self.mi] * self.kx, lat[self.mi] * 111.32])

    def snap(self, pts):
        p = np.asarray(pts)
        d, j = self.tree.query(np.c_[p[:, 1] * self.kx, p[:, 0] * 111.32])
        return self.mi[j], d / OFFROAD_KMH * 60      # node index, minutes off-road
