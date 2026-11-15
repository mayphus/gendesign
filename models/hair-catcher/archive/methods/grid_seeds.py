import itertools, math
def grid_seeds(ball):
    out = []
    for nrows, a_f, bk, al, Ro, st, be in itertools.product(
            (0, 1, 2), (0.8, 0.9, 1.0), (0.0, 0.33, 0.66, 1.0), (0, 8, 16, 24, 30),
            (12.0, 13.0, 14.0), (False, True), (40.0, 48.0)):
        a = min(6.0, ball / 2) * a_f
        bmin = a / math.tan(math.radians(45)); bmax = 9.0
        b = bmin + bk * (bmax - bmin)
        out.append(dict(Lc=5.0, t=1.6, Ro=Ro, alpha=float(al), beta=be, h_slack=0.0, d_f=ball,
                        rho1=0.0, rho2=0.0, rot1=0.0, rot2=0.0, a=a, b=b, gam=45.0, rc=0.6,
                        nrows=nrows, dN=0, v_slack=0.0, center=True, ring2=False,
                        N=0, v=0.0, stagger=st, Hs=1.0))
    return out
