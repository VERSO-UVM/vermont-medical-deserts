import csv, io, json, os, urllib.request, uuid
C='Provider Business Practice Location Address '
rows=list(csv.DictReader(open('vt_npi.csv',encoding='utf-8')))
addrs={}
for x in rows:
    k=(x['Provider First Line Business Practice Location Address'].strip().upper(),
       x[C+'City Name'].strip().upper(), x[C+'Postal Code'][:5])
    addrs.setdefault(k,len(addrs))
out='work/geocoded.json'
done=json.load(open(out)) if os.path.exists(out) else {}
todo=[(i,k) for k,i in addrs.items() if str(i) not in done]
print('unique',len(addrs),'todo',len(todo))
URL='https://geocoding.geo.census.gov/geocoder/locations/addressbatch'
for s in range(0,len(todo),1000):
    chunk=todo[s:s+1000]
    buf=io.StringIO(); w=csv.writer(buf)
    for i,(st,city,z) in chunk: w.writerow([i,st,city,'VT',z])
    b=uuid.uuid4().hex
    body=(f'--{b}\r\nContent-Disposition: form-data; name="benchmark"\r\n\r\nPublic_AR_Current\r\n'
          f'--{b}\r\nContent-Disposition: form-data; name="addressFile"; filename="a.csv"\r\nContent-Type: text/csv\r\n\r\n'
          +buf.getvalue()+f'\r\n--{b}--\r\n').encode()
    req=urllib.request.Request(URL,data=body,headers={'Content-Type':'multipart/form-data; boundary='+b})
    resp=urllib.request.urlopen(req,timeout=600).read().decode('utf-8','replace')
    for r in csv.reader(io.StringIO(resp)):
        if len(r)>5 and r[2]=='Match':
            lon,lat=map(float,r[5].split(','))
            done[r[0]]=[lat,lon]
        else:
            done.setdefault(r[0],None)
    json.dump(done,open(out,'w'))
    print(s+len(chunk),'matched so far',sum(1 for v in done.values() if v),flush=True)
json.dump({'|'.join(k):i for k,i in addrs.items()},open('work/addr_index.json','w'))
