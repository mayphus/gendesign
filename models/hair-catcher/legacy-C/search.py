"""Rank random seeds by how well their 2D cell patterns hit the size targets.

usage: python search.py <first_seed> <last_seed> <top_spacing> <bot_spacing>
e.g.   python search.py 100 150 8.2 5.2      (version C = seed 135)
"""
import sys, json, numpy as np, design as D
g = D.Grid(0.1)
res = []
for s in range(int(sys.argv[1]), int(sys.argv[2])):
    rng = np.random.default_rng(s)
    top = D.layer(rng, float(sys.argv[3]), 0.5)
    bot = D.layer(rng, float(sys.argv[4]), 0.35)
    tm, ts = D.hole_mask(g, top, 2.1, 0, 1.6, 4.6)
    bm, bs = D.hole_mask(g, bot, 1.95, 0, 1.0, 3.3)
    if not ts or not bs: continue
    ti = [o['inscribed'] for o in ts]; bi = [o['inscribed'] for o in bs]
    segs = D.strut_tree(D.junctions(top, D.OPEN_R - 0.8), D.junctions(bot, D.OPEN_R - 0.8), rng)
    oa_t = tm.sum()*0.01; oa_b = bm.sum()*0.01
    r = dict(seed=s, nt=len(ti), tmin=min(ti), tmed=float(np.median(ti)), tmax=max(ti),
             nb=len(bi), bmin=min(bi), bmed=float(np.median(bi)), bmax=max(bi),
             struts=len(segs), open_t=round(oa_t), open_b=round(oa_b))
    res.append(r)
res=[r for r in res if 12<=r['struts']<=26 and r['tmin']>=4.9 and r['bmin']>=3.4 and r['tmax']<=8.6 and r['bmax']<=5.6]
res.sort(key=lambda r: abs(r['bmed']-4.2)*3+abs(r['tmed']-6.3)-0.01*min(r['open_t'],r['open_b']))
for r in res[:8]: print(json.dumps(r))
