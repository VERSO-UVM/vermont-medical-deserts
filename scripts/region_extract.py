"""Regional comparison, step 1: providers for VT, NH, MA plus a 30-mile band of NY, ME, CT, RI.

Reads the national NPPES ZIP (work/region/nppes.zip), Census state outlines (work/region/states.zip)
and ZIP centroids (work/zcta.zip). Writes work/region/providers.csv. Run with the project venv.
"""
import csv, io, os, sys, zipfile
import shapefile
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely import affinity

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # shared modules live beside this script
from categories import cat_of  # noqa: E402

R = 'work/region/'
CORE = {'VT', 'NH', 'MA'}
BAND = {'NY', 'ME', 'CT', 'RI'}
BAND_KM = 30 * 1.609344
KX, KY = 111.32 * 0.737, 110.57          # km per degree near 42.5 N


def to_km(geom):
    return affinity.scale(geom, xfact=KX, yfact=KY, origin=(0, 0))


def state_shapes():
    r = shapefile.Reader(R + 'states.zip')
    return {rec['STUSPS']: shape(s.__geo_interface__) for s, rec in zip(r.shapes(), r.records())}


if __name__ == '__main__':
    shapes = state_shapes()
    core_km = to_km(unary_union([shapes[s] for s in CORE]))
    zc = {}
    with zipfile.ZipFile('work/zcta.zip') as z:
        for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]), encoding='utf-8'), delimiter='\t'):
            if r[0].strip().isdigit():
                zc[r[0].strip()] = (float(r[-2]), float(r[-1]))
    near = {}                                # zip5 -> within band? (cached)

    def in_band(z5):
        if z5 not in near:
            ll = zc.get(z5)
            near[z5] = bool(ll) and core_km.distance(Point(ll[1] * KX, ll[0] * KY)) <= BAND_KM
        return near[z5]

    P = 'Provider Business Practice Location Address '
    counts = {}
    with zipfile.ZipFile(R + 'nppes.zip') as z, open(R + 'providers.csv', 'w', newline='', encoding='utf-8') as out:
        name = [n for n in z.namelist() if n.lower().startswith('npidata_pfile') and n.lower().endswith('.csv')
                and 'fileheader' not in n.lower()][0]
        w = csv.writer(out)
        w.writerow(['npi', 'type', 'name', 'cat', 'code', 'state', 'addr', 'city', 'zip5'])
        for x in csv.DictReader(io.TextIOWrapper(z.open(name), encoding='utf-8')):
            st = x[P + 'State Name'].strip().upper()
            if st not in CORE and st not in BAND or x['NPI Deactivation Date'].strip():
                continue
            z5 = x[P + 'Postal Code'][:5]
            if st in BAND and not in_band(z5):
                continue
            if x['Entity Type Code'] == '1':
                nm = ' '.join(filter(None, [x['Provider First Name'], x['Provider Last Name (Legal Name)']])).title()
            else:
                nm = x['Provider Organization Name (Legal Business Name)'].title()
            code = x['Healthcare Provider Taxonomy Code_1']
            w.writerow([x['NPI'], x['Entity Type Code'], nm, cat_of(code), code, st,
                        x['Provider First Line Business Practice Location Address'].strip().upper(),
                        x[P + 'City Name'].strip().upper(), z5])
            counts[st] = counts.get(st, 0) + 1
    print('providers kept by state:', dict(sorted(counts.items())))
