#!/usr/bin/env python3
"""
Stage 1 - real topology optimisation of the hair-catcher grate.

Physics : Reissner-Mindlin plate (out-of-plane bending + transverse shear),
          4-node bilinear elements, 2x2 Gauss for bending, 1-pt for shear.
Method  : SIMP (p=3) + density filter + Heaviside projection (beta continuation),
          Optimality-Criteria update, minimise the summed compliance of several
          load cases subject to a volume fraction.
Domain  : disc inside the De40 bore (r < R_DESIGN); a passive solid seat ring
          (R_DESIGN..R_RING) that is simply supported (w = 0) where it presses on
          the bore edge; a passive solid central pinch node (r < R_NODE).
Loads   : LC1  finger press at the pinch node (lid being pushed home)
          LC2  uniform water/hair pressure on the whole grate
          LC3+ off-centre finger presses at golden-angle positions (asymmetric ->
               organic branching instead of symmetric spokes)
Output  : to_density.npy, to_history/frame_XXX.npy, to_meta.json
"""
import json, time
from pathlib import Path
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu
from scipy.ndimage import convolve

# ---------------- parameters ----------------
H        = 0.30      # element size [mm]
R_DESIGN = 16.4      # design domain radius [mm]  (inside locator ring)
R_RING   = 17.6      # outer edge of locator ring = 35.2 mm CAD OD
R_SUPP_I = 16.8      # supported annulus (ring pressed into bore) inner radius
R_NODE   = 3.4       # passive solid pinch node radius
VOLFRAC  = 0.30      # of the design domain
PENAL    = 3.0
RMIN     = 0.95      # density filter radius [mm]
E0, EMIN, NU, T = 3500.0, 3500e-6, 0.36, 1.6  # PLA, MPa, mm
F_CENTER = 6.0       # N
P_WATER  = 0.004     # N/mm^2 (generous: a fist pressing a wet hair mat)
F_OFF    = 3.0       # N
N_OFF    = 5
R_OFF    = 9.5
ITERS    = 160
SEED_ANG = 0.37      # rad, rotates the golden-angle load set (art parameter)
OUT = Path(__file__).resolve().parent
# --------------------------------------------

def element_stiffness(a):
    D_b = E0*T**3/(12*(1-NU**2))*np.array([[1,NU,0],[NU,1,0],[0,0,(1-NU)/2]])
    G = E0/(2*(1+NU)); D_s = 5/6*G*T*np.eye(2)
    xi_n = np.array([-1,1,1,-1.]); et_n = np.array([-1,-1,1,1.])
    def shape(xi, et):
        N = 0.25*(1+xi*xi_n)*(1+et*et_n)
        dNx = 0.25*xi_n*(1+et*et_n)*2/a
        dNy = 0.25*et_n*(1+xi*xi_n)*2/a
        return N, dNx, dNy
    K = np.zeros((12,12)); detJ = a*a/4
    g = 1/np.sqrt(3)
    for xi in (-g,g):
        for et in (-g,g):
            N,dx,dy = shape(xi,et); B = np.zeros((3,12))
            for i in range(4):
                B[0,3*i+1]=dx[i]; B[1,3*i+2]=dy[i]; B[2,3*i+1]=dy[i]; B[2,3*i+2]=dx[i]
            K += B.T@D_b@B*detJ
    N,dx,dy = shape(0,0); B = np.zeros((2,12))
    for i in range(4):
        B[0,3*i]=dx[i]; B[0,3*i+1]=N[i]; B[1,3*i]=dy[i]; B[1,3*i+2]=N[i]
    K += B.T@D_s@B*detJ*4
    return K/E0   # unit-modulus

def main():
    L = 2*R_RING + 2*H
    n = int(np.ceil(L/H)); L = n*H
    xc = (np.arange(n)+0.5)*H - L/2
    X, Y = np.meshgrid(xc, xc, indexing='xy')
    R = np.hypot(X, Y)
    design = R < R_DESIGN
    solid  = ((R >= R_DESIGN) & (R < R_RING)) | (R < R_NODE)
    void   = R >= R_RING
    nn = n+1
    xn = np.arange(nn)*H - L/2
    XN, YN = np.meshgrid(xn, xn, indexing='xy'); RN = np.hypot(XN, YN)
    nid = np.arange(nn*nn).reshape(nn, nn)          # [iy, ix]
    # element connectivity (counter-clockwise)
    n0 = nid[:-1,:-1].ravel(); n1 = nid[:-1,1:].ravel(); n2 = nid[1:,1:].ravel(); n3 = nid[1:,:-1].ravel()
    en = np.stack([n0,n1,n2,n3],1)
    edof = np.repeat(en*3,3,1) + np.tile([0,1,2],4)
    iK = np.repeat(edof,12,1).ravel(); jK = np.tile(edof,(1,12)).ravel()
    KE = element_stiffness(H)
    ndof = 3*nn*nn
    # supports
    fixed = list(3*nid[(RN>=R_SUPP_I)&(RN<=R_RING)])           # w = 0 on the seat
    outside_nodes = np.ones(nn*nn, bool)
    outside_nodes[np.unique(en[~void.ravel()])] = False        # nodes touching no material
    od = np.where(outside_nodes)[0]
    fixed = np.unique(np.concatenate([np.array(fixed).ravel(), 3*od, 3*od+1, 3*od+2]))
    free = np.setdiff1d(np.arange(ndof), fixed)
    # loads
    loads = []
    f = np.zeros(ndof); m = RN < 1.0; f[3*nid[m]] = -F_CENTER/m.sum(); loads.append(('center press', f, 1.0))
    f = np.zeros(ndof); m = RN < R_DESIGN; f[3*nid[m]] = -P_WATER*H*H; loads.append(('water pressure', f, 1.0))
    ga = np.pi*(3-np.sqrt(5))
    for k in range(N_OFF):
        ang = SEED_ANG + k*ga*2.0
        rr = R_OFF*(0.75+0.25*((k*0.618)%1.0)*2)
        px, py = rr*np.cos(ang), rr*np.sin(ang)
        d = np.hypot(XN-px, YN-py); m = d < 0.8
        f = np.zeros(ndof); f[3*nid[m]] = -F_OFF/m.sum()
        loads.append((f'off-centre press {k+1} @({px:.1f},{py:.1f})', f, 0.6))
    F = np.stack([l[1][free] for l in loads],1); W = np.array([l[2] for l in loads])
    # filter
    rk = int(np.ceil(RMIN/H)); g = np.arange(-rk, rk+1)*H
    GX, GY = np.meshgrid(g, g); kern = np.maximum(0, RMIN-np.hypot(GX,GY))
    act = (~void).astype(float)
    Hs = convolve(act, kern, mode='constant')
    filt = lambda x: convolve(x*act, kern, mode='constant')/np.maximum(Hs,1e-9)
    filtT = lambda g_: convolve(g_/np.maximum(Hs,1e-9), kern, mode='constant')*act
    eta = 0.5
    def proj(xt, beta):
        return (np.tanh(beta*eta)+np.tanh(beta*(xt-eta)))/(np.tanh(beta*eta)+np.tanh(beta*(1-eta)))
    def dproj(xt, beta):
        return beta*(1-np.tanh(beta*(xt-eta))**2)/(np.tanh(beta*eta)+np.tanh(beta*(1-eta)))
    x = np.where(design, VOLFRAC, 0.0); x[solid] = 1.0
    hist = OUT/'to_history'; hist.mkdir(exist_ok=True)
    beta = 1.0; log = []
    t0 = time.time()
    for it in range(1, ITERS+1):
        xt = filt(x); xp = proj(xt, beta)
        xp[solid] = 1.0; xp[void] = 0.0
        Ee = EMIN + xp.ravel()**PENAL*(E0-EMIN)
        sK = (KE.ravel()[None,:]*Ee[:,None]).ravel()
        K = sp.coo_matrix((sK,(iK,jK)),shape=(ndof,ndof)).tocsc()
        Kf = K[free][:,free]
        U = np.zeros((ndof, F.shape[1])); U[free] = splu(Kf).solve(F)
        c = 0.0; dc = np.zeros(n*n)
        for j in range(F.shape[1]):
            ue = U[edof, j]
            ce = np.einsum('ij,jk,ik->i', ue, KE, ue)
            c += W[j]*(Ee*ce).sum()
            dc += -W[j]*PENAL*xp.ravel()**(PENAL-1)*(E0-EMIN)*ce
        dc = dc.reshape(n,n)*dproj(xt,beta); dc = filtT(dc)
        dv = filtT(dproj(xt,beta)*act)
        dc[~design] = 0
        # OC with bisection on the projected volume
        l1, l2, move = 1e-9, 1e9, 0.08
        while (l2-l1)/(l1+l2) > 1e-4:
            lm = 0.5*(l1+l2)
            xn_ = np.clip(x*np.sqrt(np.maximum(-dc,0)/(np.maximum(dv,1e-12)*lm)), np.maximum(0,x-move), np.minimum(1,x+move))
            xn_[~design] = x[~design]
            vol = proj(filt(xn_),beta)[design].mean()
            if vol > VOLFRAC: l1 = lm
            else: l2 = lm
        change = np.abs(xn_-x).max(); x = xn_
        log.append(dict(it=it, c=float(c), vol=float(vol), beta=beta, change=float(change)))
        if it % 5 == 0 or it == 1:
            np.save(hist/f'frame_{it:03d}.npy', xp.astype(np.float32))
            print(f'it {it:3d} c={c:9.3f} vol={vol:.3f} beta={beta:4.1f} ch={change:.3f} t={time.time()-t0:.0f}s', flush=True)
        if it % 25 == 0 and beta < 16: beta *= 2
    xt = filt(x); xp = proj(xt, beta); xp[solid]=1; xp[void]=0
    np.save(OUT/'to_density.npy', xp.astype(np.float32))
    json.dump(dict(H=H, n=n, L=L, R_DESIGN=R_DESIGN, R_RING=R_RING, R_NODE=R_NODE, VOLFRAC=VOLFRAC,
                   PENAL=PENAL, RMIN=RMIN, T=T, loads=[l[0] for l in loads], weights=W.tolist(),
                   history=log), open(OUT/'to_meta.json','w'), indent=1)

if __name__ == '__main__':
    main()
