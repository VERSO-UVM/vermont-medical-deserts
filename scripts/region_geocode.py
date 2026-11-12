"""Regional comparison, step 2: geocode provider, hospital and rural-clinic addresses.

Uses the US Census batch geocoder; results are cached in work/region/geocoded.json (key
"ADDR|CITY|ST|ZIP5" -> [lat, lon] or null) so the script can be stopped and resumed.
Vermont addresses reuse the Vermont map's geocodes.
"""
import csv, io, json, os, uuid, urllib.request
from concurrent.futures import ThreadPoolExecutor

R = 'work/region/'
CATS = ('pc', 'mh', 'dent', 'rx')
URL = 'https://geocoding.geo.census.gov/geocoder/locations/addressbatch'


def addresses():
    keys = set()
    for r in csv.DictReader(open(R + 'providers.csv', encoding='utf-8')):
        if r['cat'] in CATS:
            keys.add((r['addr'], r['city'], r['state'], r['zip5']))
    for r in csv.DictReader(open('work/pos_q3_2026.csv', encoding='latin-1')):
        if (r['PGM_TRMNTN_CD'] == '00' and r['PRVDR_CTGRY_CD'] == '01' and r['PRVDR_CTGRY_SBTYP_CD'] in ('01', '11')
                and r['STATE_CD'] in ('VT', 'NH', 'MA', 'NY', 'ME', 'CT', 'RI')):
            keys.add((r['ST_ADR'].strip().upper(), r['CITY_NAME'].strip().upper(), r['STATE_CD'], r['ZIP_CD'][:5]))
    for st in ('NH', 'MA', 'NY', 'ME', 'CT', 'RI'):
        for r in json.load(open(R + 'rhc_%s.json' % st, encoding='utf-8')):
            keys.add((r['ADDRESS LINE 1'].strip().upper(), r['CITY'].strip().upper(), st, r['ZIP CODE'][:5]))
    return keys


def batch(chunk):
    buf = io.StringIO()
    w = csv.writer(buf)
    for i, k in enumerate(chunk):
        w.writerow([i, k[0], k[1], k[2], k[3]])
    b = uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="benchmark"\r\n\r\nPublic_AR_Current\r\n'
            f'--{b}\r\nContent-Disposition: form-data; name="addressFile"; filename="a.csv"\r\n'
            f'Content-Type: text/csv\r\n\r\n' + buf.getvalue() + f'\r\n--{b}--\r\n').encode()
    req = urllib.request.Request(URL, data=body, headers={'Content-Type': 'multipart/form-data; boundary=' + b})
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=900).read().decode('utf-8', 'replace')
            break
        except Exception as e:                       # transient server errors: retry, then give up on chunk
            print('  retry', attempt + 1, e, flush=True)
    else:
        return {}
    out = {'|'.join(k): None for k in chunk}
    for r in csv.reader(io.StringIO(resp)):
        if len(r) > 5 and r[2] == 'Match':
            lon, lat = map(float, r[5].split(','))
            out['|'.join(chunk[int(r[0])])] = [round(lat, 6), round(lon, 6)]
    return out


if __name__ == '__main__':
    cache = json.load(open(R + 'geocoded.json')) if os.path.exists(R + 'geocoded.json') else {}
    vt_idx, vt_geo = json.load(open('work/addr_index.json')), json.load(open('work/geocoded.json'))
    for k, i in vt_idx.items():                     # reuse Vermont map geocodes
        a, c, z = k.split('|')
        cache.setdefault('|'.join((a, c, 'VT', z)), vt_geo.get(str(i)))
    todo = sorted(k for k in addresses() if '|'.join(k) not in cache)
    print('to geocode', len(todo), flush=True)
    chunks = [todo[i:i + 1000] for i in range(0, len(todo), 1000)]
    with ThreadPoolExecutor(3) as ex:
        for n, res in enumerate(ex.map(batch, chunks), 1):
            cache.update(res)
            if n % 5 == 0 or n == len(chunks):
                json.dump(cache, open(R + 'geocoded.json', 'w'))
                print('  %d/%d chunks, matched so far %d' % (n, len(chunks), sum(1 for v in cache.values() if v)), flush=True)
    json.dump(cache, open(R + 'geocoded.json', 'w'))
