"""Unit test: bare silicon slab. Absorbed power must equal the Fresnel
transmittance times the Beer-Lambert factor."""
import numpy as np
import meep as mp
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bxsim import materials as M

wl = 0.55
fcen = 1.0 / wl
res = int(sys.argv[1]) if len(sys.argv) > 1 else 40
n_si = float(M.si_n(550.0)); k_si = float(M.si_alpha_per_um(550.0) * wl / (4 * np.pi))
eps = n_si**2 - k_si**2
si = mp.Medium(epsilon=eps, D_conductivity=2*np.pi*fcen*(2*n_si*k_si)/eps)

sx = sy = 0.8
t_si, t_air, dpml = 3.0, 1.5, 1.0
sz = dpml + t_air + t_si + dpml
zc = 0.5 * ((t_air + dpml) + (-t_si - dpml))     # z=0 at Si surface
src_z = 0.6 - zc
vol = mp.Volume(center=mp.Vector3(0, 0, -t_si/2 - zc), size=mp.Vector3(sx, sy, t_si))

def make(vacuum):
    geom = [] if vacuum else [mp.Block(size=mp.Vector3(mp.inf, mp.inf, t_si + dpml),
                                       center=mp.Vector3(0, 0, -(t_si+dpml)/2 - zc),
                                       material=si)]
    src = [mp.Source(mp.GaussianSource(fcen, fwidth=0.15*fcen), component=mp.Ex,
                     center=mp.Vector3(0, 0, src_z), size=mp.Vector3(sx, sy, 0))]
    syms = ([mp.Mirror(mp.X, phase=-1), mp.Mirror(mp.Y, phase=+1)]
            if len(sys.argv) > 2 and sys.argv[2] == "sym" else [])
    return mp.Simulation(cell_size=mp.Vector3(sx, sy, sz), geometry=geom, sources=src,
                         resolution=res, boundary_layers=[mp.PML(dpml, direction=mp.Z)],
                         k_point=mp.Vector3(), default_material=mp.air,
                         symmetries=syms)

ref = make(True)
fr = mp.FluxRegion(center=mp.Vector3(0, 0, -zc), size=mp.Vector3(sx, sy, 0), direction=mp.Z)
fl = ref.add_flux(fcen, 0, 1, fr)
pvol = mp.Volume(center=mp.Vector3(0, 0, -zc), size=mp.Vector3(sx, sy, 0))
pdft = ref.add_dft_fields([mp.Ex, mp.Ey, mp.Ez], fcen, 0, 1, where=pvol)
ref.run(until_after_sources=60)
p_inc_flux = abs(mp.get_fluxes(fl)[0])
# same machinery as the absorbed power: in vacuum a downward plane wave of DFT
# amplitude E carries 0.5*|E|^2 per unit area (c = eps0 = mu0 = 1 in Meep units)
E2p = sum(np.abs(ref.get_dft_array(pdft, c, 0))**2 for c in (mp.Ex, mp.Ey, mp.Ez))
_, _, _, wp = ref.get_array_metadata(vol=pvol)
p_inc = 0.5 * float((E2p * np.asarray(wp).reshape(E2p.shape)).sum())

sim = make(False)
dft = sim.add_dft_fields([mp.Ex, mp.Ey, mp.Ez], fcen, 0, 1, where=vol)
sim.run(until_after_sources=mp.stop_when_fields_decayed(20, mp.Ex,
        mp.Vector3(0, 0, -t_si/2 - zc), 1e-6))
E2 = sum(np.abs(sim.get_dft_array(dft, c, 0))**2 for c in (mp.Ex, mp.Ey, mp.Ez))
xs, ys, zs, w = sim.get_array_metadata(vol=vol)
w = np.asarray(w).reshape(E2.shape)
P = 0.5 * (2*np.pi*fcen) * (2*n_si*k_si) * E2
absorbed = float((P * w).sum())

if mp.am_master():
    R = ((n_si-1)**2 + k_si**2) / ((n_si+1)**2 + k_si**2)
    alpha = M.si_alpha_per_um(550.0)
    analytic = (1 - R) * (1 - np.exp(-alpha * t_si))
    print("\n--- diagnostics ---")
    print("sum(w) = %.4f   (Si volume = %.4f um^3)" % (w.sum(), sx*sy*t_si))
    print("p_inc(add_flux)     = %.6g" % p_inc_flux)
    print("p_inc(dft |E|^2/2)  = %.6g   ratio = %.4f" % (p_inc, p_inc_flux / p_inc))
    print("absorbed = %.6g" % absorbed)
    print("absorbed / p_inc = %.4f" % (absorbed / p_inc))
    print("analytic (1-R)*(1-exp(-a t)) = %.4f   [R=%.4f]" % (analytic, R))
