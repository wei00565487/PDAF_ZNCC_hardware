"""Physics sanity checks. Run this first -- it validates the solvers."""
import sys, time, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
from bxsim import PixelStack, Simulator, materials as M, optics, diffusion

ok = lambda c: "OK " if c else "FAIL"

print("=== 1. silicon optical constants ===")
for w in (450, 550, 650, 850, 940):
    print(f"  {w} nm: n={M.si_n(w):.3f}  alpha={M.si_alpha_per_um(w)*1e4:.3g} /cm"
          f"  1/alpha={M.si_absorption_depth_um(w):.3f} um")
print(f"  ARC T(550nm) = {M.arc_transmittance(550):.3f}  (bare Si would be ~0.68)")

print("\n=== 2. optical energy budget (5x5 array, all CFA cells open) ===")
s = PixelStack(n_pix=3, si_thickness_um=3.0, dti_enabled=False)
for w in (450, 550, 650, 850):
    G = optics.generation(s, w, aperture="all")
    T = M.arc_transmittance(w)
    print(f"  {w} nm: absorbed/pixel = {G.sum()/s.n_pix**2:.4f}"
          f"   ARC-limited max = {T:.4f}"
          f"   Beer-Lambert = {T*(1-np.exp(-M.si_alpha_per_um(w)*s.si_thickness_um)):.4f}")

print("\n=== 3. adjoint transport: partition of unity ===")
s2 = PixelStack(n_pix=3, dti_enabled=False, s_back_cm_s=0.0, s_front_cm_s=0.0,
                lifetime_us=1e6)
t0 = time.time()
u = diffusion.collection_map(s2, verbose=True)
print(f"  solve time {time.time()-t0:.1f} s")
n = int(round(s2.pitch_um / (s2.dx_diff_nm*1e-3)))
tot = sum(np.roll(u, (i*n, j*n), axis=(1, 2))
          for i in range(-1, 2) for j in range(-1, 2))
print(f"  sum over all PDs: min={tot.min():.6f} max={tot.max():.6f} "
      f"-> {ok(abs(tot.min()-1) < 2e-3 and abs(tot.max()-1) < 2e-3)}")
print(f"  u in [0,1]: {ok(u.min() > -1e-6 and u.max() < 1+1e-6)}")

print("\n=== 4. crosstalk kernel row sums vs total QE ===")
s3 = PixelStack(n_pix=3, dti_enabled=True)
sim = Simulator(s3)
for w in (450, 550, 650, 850):
    K = sim.kernel(w)
    print(f"  {w} nm  QE_own={K[1,1]:.4f}  QE_total={K.sum():.4f}"
          f"  crosstalk={(K.sum()-K[1,1])/max(K.sum(),1e-12)*100:5.1f} %")
