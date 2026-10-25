"""Independent NumPy/C equivalence and known-position controls; no images are persisted."""
from privacy import sample,templates,match,match_numpy
cases=[('ar','s2-quote-photo',8,(806,880)),('en','s2-quote-photo',8,(979,880)),
       ('ar','s4-phone-approve',5,(248,84)),('en','s4-phone-approve',5,(16,84)),
       ('ar','s4-phone-approve',9,(43,235)),('en','s4-phone-approve',9,(97,235)),
       ('ar','s1-rfq',20,None)]
ts=templates()
for lang,name,t,point in cases:
    g=sample(lang,name,t);native=match(g,ts);numpy=match_numpy(g,ts)
    assert sorted(native)==sorted(numpy),(lang,name,t,native,numpy)
    assert (any(tuple(h[1:3])==point for h in native) if point else not native)
    print('DETECTOR_EQUIVALENCE',lang,name,f'{t}s',f'matches={len(native)}',flush=True)
print('PASS: seven native-resolution positive/negative controls; C and NumPy agree')
