"""Build app/data.js for the Vermont provider map from vt_npi.csv + geocodes."""
import csv, io, json, zipfile

W = 'work/'
C = 'Provider Business Practice Location Address '

CATS = [  # (key, label, taxonomy prefixes) - first match wins
    ('mh', 'Mental & behavioral health', ['101Y', '103', '104', '106', '2084P', '2084A', '2084B',
                                          '363LP', '261QM', '3245', '320', '2083A']),
    ('pc', 'Primary care', ['207Q', '207R', '208D', '2080', '363LF', '363LA', '363LG', '363LP',
                            '363L0', '261QP0300', '261QF0400', '261QR1300', '261QC1500']),
    ('dent', 'Dental', ['122', '124', '1223', '126']),
    ('rx', 'Pharmacy', ['1835', '3336']),
    ('rehab', 'Rehab & therapy (PT/OT/speech)', ['2251', '225X', '235Z', '2255', '2257', '2278', '2279', '2256']),
    ('spec', 'Specialist physicians', ['20']),
    ('hosp', 'Hospitals & facilities', ['27', '28', '31', '261Q']),
    ('nurse', 'Nursing, NP/PA, midwifery', ['163W', '164', '363', '367']),
    ('comm', 'Home & community support', ['171M', '172V', '251', '253', '374', '372', '376']),
    ('sn', 'Safety-net clinics (FQHC & RHC sites)', []),     # from HRSA/CMS, not NPPES taxonomy
    ('other', 'Other / students', ['']),
]
# Medicare billing data only says something about clinicians Medicare pays directly
MCR_CATS = ['pc', 'spec', 'nurse']


def cat_of(code):
    for key, _, prefixes in CATS:
        if any(code.startswith(p) for p in prefixes):
            return key
    return 'other'


def pip(x, y, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]; xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_geom(lon, lat, g):
    polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
    for poly in polys:
        if pip(lon, lat, poly[0]) and not any(pip(lon, lat, h) for h in poly[1:]):
            return True
    return False


# ZIP centroids as a fallback for addresses the geocoder could not match
zc = {}
with zipfile.ZipFile(W + 'zcta.zip') as z:
    f = io.TextIOWrapper(z.open(z.namelist()[0]), encoding='utf-8')
    for r in csv.reader(f, delimiter='\t'):
        if r[0].strip().isdigit():
            zc[r[0].strip()] = (float(r[-2]), float(r[-1]))

geo = json.load(open(W + 'geocoded.json'))
idx = json.load(open(W + 'addr_index.json'))
towns = json.load(open(W + 'vt_towns.geojson'))

# Medicare Part B patients per individual NPI, 2024 (0 = did not bill Medicare in their own name)
mcr = {r['Rndrng_NPI']: int(r['Tot_Benes'] or 0)
       for r in json.load(open(W + 'medicare/vt_0.json', encoding='utf-8'))}

locs = {}
stats = {'exact': 0, 'zip': 0, 'none': 0}
for x in csv.DictReader(open('vt_npi.csv', encoding='utf-8')):
    st = x['Provider First Line Business Practice Location Address'].strip().upper()
    city = x[C + 'City Name'].strip().upper()
    z5 = x[C + 'Postal Code'][:5]
    i = str(idx['|'.join((st, city, z5))])
    ll, approx = geo.get(i), 0
    if not ll and z5 in zc:
        ll, approx = zc[z5], 1
    if not ll:
        stats['none'] += 1
        continue
    stats['zip' if approx else 'exact'] += 1
    if x['Entity Type Code'] == '1':
        name = ' '.join(filter(None, [x['Provider First Name'], x['Provider Last Name (Legal Name)']])).title()
        cred = x['Provider Credential Text'].strip()
        if cred:
            name += ', ' + cred
    else:
        name = x['Provider Organization Name (Legal Business Name)'].title()
    code = x['Healthcare Provider Taxonomy Code_1']
    loc = locs.setdefault(i, {'ll': [round(ll[0], 5), round(ll[1], 5)], 'a': approx,
                              'addr': st.title() + ', ' + city.title() + ' ' + z5, 'p': []})
    loc['p'].append([name, cat_of(code), code, int(x['Entity Type Code']), mcr.get(x['NPI'], 0)])

# safety-net sites: HRSA health center (FQHC) sites + CMS-enrolled rural health clinics.
# School-based and nursing-home sites serve only their own students/residents, so they are
# shown on the map but not used for drive times.
schools = []
for r in csv.DictReader(open(W + 'hrsa/Health_Center_Service_Delivery_and_LookAlike_Sites.csv', encoding='utf-8-sig')):
    if r['Site State Abbreviation'] != 'VT' or r['Site Status Description'] != 'Active':
        continue
    ll = [round(float(r['Geocoding Artifact Address Primary Y Coordinate']), 5),
          round(float(r['Geocoding Artifact Address Primary X Coordinate']), 5)]
    setting = r['Health Center Service Delivery Site Location Setting Description']
    name = r['Site Name'].strip() + ' (' + r['Health Center Name'].title() + ')'
    addr = r['Site Address'].title() + ', ' + r['Site City'].title() + ' ' + r['Site Postal Code'][:5]
    if setting in ('School', 'Nursing Home'):
        schools.append({'ll': ll, 'name': name, 'addr': addr, 'setting': setting})
        continue
    locs['fqhc' + r['BPHC Assigned Number']] = {
        'll': ll, 'a': 0, 'addr': addr, 'p': [[name, 'sn', 'FQHC', 2, 0]]}
rhc_geo = json.load(open(W + 'rhc_geo.json'))
for i, r in enumerate(json.load(open(W + 'rhc_vt.json', encoding='utf-8'))):
    if str(i) in rhc_geo:
        name = (r['DOING BUSINESS AS NAME'] or r['ORGANIZATION NAME']).title()
        locs['rhc%d' % i] = {'ll': rhc_geo[str(i)], 'a': 0,
                             'addr': r['ADDRESS LINE 1'].title() + ', ' + r['CITY'].title() + ' ' + r['ZIP CODE'][:5],
                             'p': [[name, 'sn', 'RHC', 2, 0]]}

# assign each location to a town
for loc in locs.values():
    lat, lon = loc['ll']
    loc['t'] = next((t['properties']['TOWNNAME'].title() for t in towns['features']
                     if in_geom(lon, lat, t['geometry'])), None)

# grid of ~1.5 km cells inside Vermont for the gap layer
dlat, dlon = 0.0135, 0.019
names = [t['properties']['TOWNNAME'].title() for t in towns['features']]
cells, cell_town = [], []
lat = 42.72
while lat < 45.02:
    lon = -73.44
    while lon < -71.46:
        c = (lon + dlon / 2, lat + dlat / 2)
        k = next((k for k, t in enumerate(towns['features']) if in_geom(c[0], c[1], t['geometry'])), None)
        if k is not None:
            cells.append([round(lat, 4), round(lon, 4)])
            cell_town.append(k)
        lon += dlon
    lat += dlat


def thin(ring, step=0.0006):
    """Drop vertices within ~60 m of the previous kept one (town outlines only)."""
    out = [ring[0]]
    for x, y in ring[1:-1]:
        if abs(x - out[-1][0]) > step or abs(y - out[-1][1]) > step:
            out.append([x, y])
    return [[round(x, 4), round(y, 4)] for x, y in out + [ring[-1]]]


for t in towns['features']:
    g = t['geometry']
    polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
    t['geometry'] = {'type': 'MultiPolygon', 'coordinates': [[thin(r) for r in p] for p in polys]}
    t['properties'] = {'name': t['properties']['TOWNNAME'].title()}
    t.pop('id', None)
towns.pop('crs', None)

out = {'cats': [[k, l] for k, l, _ in CATS], 'mcrCats': MCR_CATS, 'locs': list(locs.values()),
       'schools': schools, 'towns': names,
       'grid': {'dlat': dlat, 'dlon': dlon, 'cells': cells, 'town': cell_town}}
with open('app/data.js', 'w', encoding='utf-8') as f:
    f.write('window.DATA=' + json.dumps(out, separators=(',', ':')) + ';\n')
    f.write('window.TOWNS=' + json.dumps(towns, separators=(',', ':')) + ';\n')
print(stats, 'locations', len(locs), 'grid cells', len(cells),
      'no town', sum(1 for l in locs.values() if not l['t']))
