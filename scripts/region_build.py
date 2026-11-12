"""Regional comparison, step 3: drive-time access for Vermont, New Hampshire and Massachusetts.

For every 2020 census block in the three states, computes the drive time to the nearest provider in
each category, two ways:
  own    - only providers in the resident's own state
  region - providers anywhere in VT/NH/MA or within 30 miles in NY, ME, CT, RI
Writes app/compare-data.js (summary tables + a 1.5 km overview grid). Run with the project venv after
region_extract.py and region_geocode.py.
"""
import base64, csv, io, json, os, sys, time, zipfile
import numpy as np
import shapefile
from scipy.sparse import coo_matrix, bmat
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely import contains_xy
from shapely.geometry import shape, Point
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # shared modules live beside this script
from roadnet import build, Snapper            # noqa: E402
from census import read_blocks                # noqa: E402
from region_extract import to_km, KX, KY, BAND_KM, CORE   # noqa: E402

R = 'work/region/'
STATES = ['VT', 'NH', 'MA']
NAMES = {'VT': 'Vermont', 'NH': 'New Hampshire', 'MA': 'Massachusetts'}
CATS = [('pc', 'Primary care'), ('mh', 'Mental & behavioral health'), ('dent', 'Dental'),
        ('rx', 'Pharmacy'), ('hosp', 'Hospital (acute or critical access)'), ('sn', 'Safety-net clinic (FQHC/RHC)')]
THRESHOLDS = [15, 20, 30, 45]
BBOX = (41.2, -74.4, 45.35, -69.85)           # south, west, north, east: core states + 30-mile band
DLAT, DLON = 0.0135, 0.019                    # same 1.5 km grid as the Vermont map
t0 = time.time()


def log(*a):
    print('%4.0fs' % (time.time() - t0), *a, flush=True)


# ---- geography ----
rdr = shapefile.Reader(R + 'states.zip')
shapes = {rec['STUSPS']: shape(s.__geo_interface__) for s, rec in zip(rdr.shapes(), rdr.records())}
core_km = to_km(unary_union([shapes[s] for s in CORE]))


def in_reach(st, lat, lon):
    return st in CORE or core_km.distance(Point(lon * KX, lat * KY)) <= BAND_KM


zc = {}
with zipfile.ZipFile('work/zcta.zip') as z:
    for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding='utf-8'), delimiter='\t'):
        if r[0].strip().isdigit():
            zc[r[0].strip()] = (float(r[-2]), float(r[-1]))
geo = json.load(open(R + 'geocoded.json'))


def locate(addr, city, st, z5):
    """Street geocode, else ZIP centroid (as on the Vermont map), else None."""
    ll = geo.get('|'.join((addr, city, st, z5)))
    return (ll[0], ll[1], 0) if ll else ((*zc[z5], 1) if z5 in zc else None)


# ---- provider locations: cat -> list of (lat, lon, state) ----
locs = {c: set() for c, _ in CATS}
stats = {'exact': 0, 'zip': 0, 'none': 0}
supply = {s: {c: 0 for c, _ in CATS} for s in STATES}       # individual clinicians by practice state
for r in csv.DictReader(open(R + 'providers.csv', encoding='utf-8')):
    if r['cat'] not in ('pc', 'mh', 'dent', 'rx'):
        continue
    if r['state'] in STATES and r['type'] == '1':
        supply[r['state']][r['cat']] += 1
    ll = locate(r['addr'], r['city'], r['state'], r['zip5'])
    stats['none' if ll is None else 'zip' if ll[2] else 'exact'] += 1
    if ll:
        locs[r['cat']].add((round(ll[0], 5), round(ll[1], 5), r['state']))

beds = {s: 0 for s in STATES}
for r in csv.DictReader(open('work/pos_q3_2026.csv', encoding='latin-1')):
    st = r['STATE_CD']
    if (r['PGM_TRMNTN_CD'] == '00' and r['PRVDR_CTGRY_CD'] == '01' and r['PRVDR_CTGRY_SBTYP_CD'] in ('01', '11')
            and st in ('VT', 'NH', 'MA', 'NY', 'ME', 'CT', 'RI')):
        ll = locate(r['ST_ADR'].strip().upper(), r['CITY_NAME'].strip().upper(), st, r['ZIP_CD'][:5])
        if ll and in_reach(st, ll[0], ll[1]):
            locs['hosp'].add((ll[0], ll[1], st))
            if st in STATES:
                supply[st]['hosp'] += 1
                beds[st] += int(r['CRTFD_BED_CNT'] or 0)

for r in csv.DictReader(open('work/hrsa/Health_Center_Service_Delivery_and_LookAlike_Sites.csv', encoding='utf-8-sig')):
    st = r['Site State Abbreviation']
    if (st in ('VT', 'NH', 'MA', 'NY', 'ME', 'CT', 'RI') and r['Site Status Description'] == 'Active'
            and r['Health Center Service Delivery Site Location Setting Description'] not in ('School', 'Nursing Home')):
        la, lo = float(r['Geocoding Artifact Address Primary Y Coordinate']), float(r['Geocoding Artifact Address Primary X Coordinate'])
        if in_reach(st, la, lo):
            locs['sn'].add((la, lo, st))
            if st in STATES:
                supply[st]['sn'] += 1
rhc_vt_geo = json.load(open('work/rhc_geo.json'))
for ll in rhc_vt_geo.values():
    locs['sn'].add((ll[0], ll[1], 'VT')); supply['VT']['sn'] += 1
for st in ('NH', 'MA', 'NY', 'ME', 'CT', 'RI'):
    for r in json.load(open(R + 'rhc_%s.json' % st, encoding='utf-8')):
        ll = locate(r['ADDRESS LINE 1'].strip().upper(), r['CITY'].strip().upper(), st, r['ZIP CODE'][:5])
        if ll and in_reach(st, ll[0], ll[1]):
            locs['sn'].add((ll[0], ll[1], st))
            if st in STATES:
                supply[st]['sn'] += 1
log('provider rows', stats, {c: len(v) for c, v in locs.items()})

# ---- population and grid ----
blocks = {s: read_blocks((R + 'census/%s2020.dhc.zip' % s.lower()) if s != 'VT' else 'work/census/vt2020.dhc.zip', s)
          for s in STATES}
pop_tot = {s: int(b[:, 2].sum()) for s, b in blocks.items()}
log('population', pop_tot)

cells, cell_state = [], []
la_ = np.arange(41.2, 45.05, DLAT)
lo_ = np.arange(-73.55, -69.85, DLON)
LO, LA = np.meshgrid(lo_ + DLON / 2, la_ + DLAT / 2)
for k, s in enumerate(STATES):
    inside = contains_xy(shapes[s], LO.ravel(), LA.ravel())
    for i in np.nonzero(inside)[0]:
        cells.append((LA.ravel()[i] - DLAT / 2, LO.ravel()[i] - DLON / 2)); cell_state.append(k)
cells = np.array(cells)
log('grid cells', len(cells))

# ---- road network ----
files = ['work/osm/vermont-latest.osm.pbf'] + ['%sosm/%s-latest.osm.pbf' % (R, s) for s in
                                                ('new-hampshire', 'massachusetts', 'new-york', 'maine', 'connecticut', 'rhode-island')]
lat, lon, G = build(files, BBOX)
snap = Snapper(lat, lon, G, ref_lat=42.8, main_only=False).snap
n = G.shape[0]
bnode = {s: snap(b[:, :2]) for s, b in blocks.items()}
cnode, coff = snap(cells + [DLAT / 2, DLON / 2])
cell_pop = np.zeros(len(cells))
for s, b in blocks.items():                   # residents per cell, for the overview map
    mask = np.array(cell_state) == STATES.index(s)
    idx = np.nonzero(mask)[0]
    _, j = cKDTree(np.c_[cells[idx, 0] + DLAT / 2, (cells[idx, 1] + DLON / 2) * 0.73]).query(np.c_[b[:, 0], b[:, 1] * 0.73])
    cell_pop += np.bincount(idx[j], weights=b[:, 2], minlength=len(cells))
log('snapped')


def minutes_from(points):
    """Drive minutes from the nearest of `points` to every routing node (virtual super-source)."""
    if not points:
        return np.full(n, np.inf)
    pn, poff = snap(np.array([p[:2] for p in points]))
    best = {}
    for a, o in zip(pn, poff):
        best[a] = min(best.get(a, np.inf), o)
    row = coo_matrix((np.array(list(best.values())) + 1e-6, (np.zeros(len(best), int), np.array(list(best)))), shape=(1, n))
    A = bmat([[G, None], [row, coo_matrix((1, 1))]], format='csr')
    return dijkstra(A, directed=True, indices=n)[:n]


def summarise(m, b):
    """Population-weighted results for one state's blocks given minutes per block."""
    out = {}
    for name, col in (('all', 2), ('o65', 4), ('u18', 3)):
        w = b[:, col]
        out[name] = [round(100 * w[m > t].sum() / w.sum(), 2) for t in THRESHOLDS]
        out[name + '_n'] = [int(w[m > t].sum()) for t in THRESHOLDS]
    w = b[:, 2]
    order = np.argsort(m)
    out['median'] = round(min(float(m[order][np.searchsorted(np.cumsum(w[order]), w.sum() / 2)]), 999), 1)
    out['mean'] = round(float((np.minimum(m, 90) * w).sum() / w.sum()), 1)
    return out


results, grids = {}, {}
for c, label in CATS:
    region = minutes_from(list(locs[c]))
    results[c] = {}
    own_cells = np.full(len(cells), 255.0)
    for k, s in enumerate(STATES):
        own = minutes_from([p for p in locs[c] if p[2] == s])
        bn, bo = bnode[s]
        results[c][s] = {'region': summarise(region[bn] + bo, blocks[s]), 'own': summarise(own[bn] + bo, blocks[s])}
        mask = np.array(cell_state) == k
        own_cells[mask] = own[cnode[mask]] + coff[mask]
    grids[c] = {'region': region[cnode] + coff, 'own': own_cells}
    log(c, {s: (results[c][s]['own']['all'][1], results[c][s]['region']['all'][1]) for s in STATES}, '(% beyond 20 min: own, region)')

# ---- shortage areas: residents in designated area HPSAs ----
hpsa = {}
for key, code in (('pc', 'PC'), ('dent', 'DH'), ('mh', 'MH')):
    seen, tot = set(), {s: 0 for s in STATES}
    for r in csv.DictReader(open('work/hrsa/BCD_HPSA_FCT_DET_%s.csv' % code, encoding='utf-8-sig')):
        s = r['Primary State Abbreviation']
        if (s in STATES and r['HPSA Status'] in ('Designated', 'Proposed For Withdrawal')
                and r['Designation Type'] in ('Geographic HPSA', 'High Needs Geographic HPSA', 'HPSA Population')
                and r['HPSA ID'] not in seen):
            seen.add(r['HPSA ID'])
            tot[s] += int(float(r['HPSA Designation Population'] or 0))
    hpsa[key] = {s: round(100 * v / pop_tot[s], 1) for s, v in tot.items()}

# ---- write ----
u8 = lambda a: base64.b64encode(np.clip(np.rint(np.nan_to_num(a, posinf=255)), 0, 255).astype(np.uint8).tobytes()).decode()
rows_ = np.rint((cells[:, 0] - 41.2) / DLAT).astype(np.uint16)
cols_ = np.rint((cells[:, 1] + 73.55) / DLON).astype(np.uint16)


def outline(s, step=0.004):
    g = shapes[s].simplify(step)
    polys = [g] if g.geom_type == 'Polygon' else list(g.geoms)
    return {'type': 'Feature', 'properties': {'state': s},
            'geometry': {'type': 'MultiPolygon', 'coordinates': [[[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords]]
                                                                 for p in polys if p.area > 1e-4]}}


out = {
    'states': [[s, NAMES[s], pop_tot[s]] for s in STATES], 'cats': CATS, 'thresholds': THRESHOLDS,
    'results': results, 'hpsa': hpsa,
    'supply': {s: {**{c: round(10000 * supply[s][c] / pop_tot[s], 1) for c in ('pc', 'mh', 'dent', 'rx')},
                   'hosp': supply[s]['hosp'], 'beds': round(1000 * beds[s] / pop_tot[s], 2),
                   'sn': round(100000 * supply[s]['sn'] / pop_tot[s], 1)} for s in STATES},
    'grid': {'lat0': 41.2, 'lon0': -73.55, 'dlat': DLAT, 'dlon': DLON,
             'row': base64.b64encode(rows_.tobytes()).decode(), 'col': base64.b64encode(cols_.tobytes()).decode(),
             'pop': base64.b64encode(np.minimum(np.rint(cell_pop), 65535).astype(np.uint16).tobytes()).decode(),
             'min': {c: {v: u8(g[v]) for v in ('region', 'own')} for c, g in grids.items()}},
    'outlines': {'type': 'FeatureCollection', 'features': [outline(s) for s in STATES]},
    'geocode': stats,
}
with open('app/compare-data.js', 'w', encoding='utf-8') as f:
    f.write('window.CMP=' + json.dumps(out, separators=(',', ':')) + ';\n')
log('wrote app/compare-data.js')
