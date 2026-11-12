"""Vermont Health Professional Shortage Area (HPSA) boundaries -> app/hpsa.js.

Reads HRSA's "Area HPSA Component Boundaries" shapefiles (work/hrsa/HPSA_CMP{PC,DH,MH}_SHP.zip,
from https://data.hrsa.gov/data/download) and keeps Vermont components that are designated
or proposed for withdrawal. Run with the project venv (needs pyshp).
"""
import json
import shapefile

KINDS = {'pc': 'PC', 'dent': 'DH', 'mh': 'MH'}
KEEP = ('Designated', 'Proposed For Withdrawal')


def thin(ring, step=0.002):
    """Drop vertices closer than ~200 m to the previous kept one; plenty for a statewide overlay."""
    out = [ring[0]]
    for x, y in ring[1:]:
        if abs(x - out[-1][0]) > step or abs(y - out[-1][1]) > step:
            out.append((x, y))
    out.append(ring[-1])
    return [[round(x, 4), round(y, 4)] for x, y in out]


out = {}
for key, code in KINDS.items():
    r = shapefile.Reader('work/hrsa/HPSA_CMP%s_SHP.zip' % code)
    feats = []
    for sr in r.iterShapeRecords():
        d = sr.record.as_dict()
        if d['CmpStAbbr'] != 'VT' or d['HpsStatDes'] not in KEEP:
            continue
        g = sr.shape.__geo_interface__
        polys = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        polys = [[thin(ring) for ring in poly] for poly in polys]
        feats.append({'type': 'Feature',
                      'geometry': {'type': 'MultiPolygon', 'coordinates': polys},
                      'properties': {'name': d['HpsNM'], 'part': d['CmpNM'], 'type': d['HpsTypDes'],
                                     'pop': d['HpsPpTypDe'], 'score': d['HpsScore'],
                                     'status': d['HpsStatDes'], 'updated': str(d['HpsDgnLUDT'] or '')}})
    out[key] = {'type': 'FeatureCollection', 'features': feats}
    print(key, len(feats), 'components')

with open('app/hpsa.js', 'w', encoding='utf-8') as f:
    f.write('window.HPSA=' + json.dumps(out, separators=(',', ':')) + ';\n')
