"""Rigorous 3-D FDTD cross-check of the optical half of the model (Meep, free).

The BPM in `bxsim/optics.py` is scalar and one-way: it cannot see polarisation,
back-reflections, or the *reflecting* behaviour of an oxide-filled trench (it
treats DTI as an absorber).  This script solves the same stack with MIT's Meep
FDTD, writes the absorbed-power map on the same grid `bxsim` uses, and prints
the per-pixel optical split so the two can be compared.

Absolute normalisation is done with a second, empty (vacuum) run that measures
the power the source sends downwards through the same plane, so the printed QE
is "absorbed photons / photons incident on one pixel area" -- the same
definition `bxsim` uses.

The output .npz plugs straight back into the carrier-transport solver:

    import numpy as np
    from bxsim import PixelStack, diffusion
    d = np.load("meep/out/fdtd_550nm_center.npz")
    st = PixelStack(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, ...)
    K = diffusion.collect(d["G"], diffusion.collection_map(st), st)

Install (WSL / Ubuntu):
    sudo apt install python3-meep-mpi-default python3-scipy
Run:
    python3 pixel_fdtd.py --wavelength 550 --resolution 30 --cell-pixels 3
    mpirun -np 8 python3 pixel_fdtd.py ...        # parallel
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import time

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from bxsim import materials as M                                   # noqa: E402

try:
    import meep as mp
except ImportError:                                                # pragma: no cover
    raise SystemExit("Meep not found.  sudo apt install python3-meep-mpi-default")
if not hasattr(mp, "Simulation"):                                  # pragma: no cover
    raise SystemExit(
        "The local meep/ directory was imported instead of MIT Meep. "
        "Activate the pymeep environment; see meep/environment.yml.")


def geometry_of(args):
    """Layer positions with z = 0 at the Si back surface, +z towards the lens."""
    g = argparse.Namespace()
    g.t_air = 0.60
    g.dpml = 1.00
    g.z_arc_top = args.d_arc
    g.z_cfa_bot = g.z_arc_top + args.t_cfa_to_si
    g.z_cfa_top = g.z_cfa_bot + args.t_cfa
    g.z_ircf_top = g.z_cfa_top + args.t_ircf
    g.z_ml_base = g.z_ircf_top + args.t_ml_to_cfa
    g.z_top = g.z_ml_base + args.ml_sag + g.t_air + g.dpml
    g.z_bot = -args.si_thickness - g.dpml
    g.zc = 0.5 * (g.z_top + g.z_bot)
    g.sz = g.z_top - g.z_bot
    g.sx = g.sy = args.cell_pixels * args.pitch
    g.src_z = g.z_ml_base + args.ml_sag + 0.35 * g.t_air
    return g


def ml_roc(args):
    """Radius of a gapless spherical cap of height `ml_sag` over a square cell."""
    if args.ml_roc is not None:
        return args.ml_roc
    a = args.pitch / np.sqrt(2.0)
    h = args.ml_sag
    return (a * a + h * h) / (2 * h)


def build(args, vacuum=False):
    g = geometry_of(args)
    wl = args.wavelength * 1e-3
    fcen = 1.0 / wl
    n_si = float(M.si_n(args.wavelength))
    k_si = float(M.si_alpha_per_um(args.wavelength) * wl / (4 * np.pi))
    eps_si = n_si ** 2 - k_si ** 2

    geom = []
    if not vacuum:
        si = mp.Medium(epsilon=eps_si,
                       D_conductivity=2 * np.pi * fcen * (2 * n_si * k_si) / eps_si)
        ml = mp.Medium(index=M.N_MICROLENS)
        pl = mp.Medium(index=M.N_PLANAR)
        arc = mp.Medium(index=M.N_ARC)
        cfa_clear = mp.Medium(index=M.N_CFA)
        # a CFA cell we want to block: strongly absorbing, same real index
        cfa_black = mp.Medium(epsilon=M.N_CFA ** 2,
                              D_conductivity=2 * np.pi * fcen * 4.0 / M.N_CFA ** 2)

        R = ml_roc(args)
        n, off = args.cell_pixels, (args.cell_pixels - 1) / 2.0
        for i in range(n):
            for j in range(n):
                geom.append(mp.Sphere(
                    radius=R, material=ml,
                    center=mp.Vector3((i - off) * args.pitch + args.ml_shift,
                                      (j - off) * args.pitch,
                                      g.z_ml_base + args.ml_sag - R - g.zc)))
        # everything below the microlens base plane is planarisation
        geom.append(mp.Block(
            size=mp.Vector3(mp.inf, mp.inf, g.z_ml_base - g.z_bot),
            center=mp.Vector3(0, 0, 0.5 * (g.z_ml_base + g.z_bot) - g.zc),
            material=pl))
        for i in range(n):
            for j in range(n):
                centre = (i == n // 2 and j == n // 2)
                mat = cfa_clear if (args.aperture == "all" or centre) else cfa_black
                geom.append(mp.Block(
                    size=mp.Vector3(args.pitch, args.pitch, args.t_cfa),
                    center=mp.Vector3((i - off) * args.pitch, (j - off) * args.pitch,
                                      0.5 * (g.z_cfa_bot + g.z_cfa_top) - g.zc),
                    material=mat))
        # low-index grid walls inside the colour-filter layer
        if args.cfa_grid_width > 0:
            grid = mp.Medium(index=args.n_cfa_grid)
            for k in range(n + 1):
                e = (k - n / 2.0) * args.pitch
                geom.append(mp.Block(
                    size=mp.Vector3(args.cfa_grid_width, mp.inf, args.t_cfa),
                    center=mp.Vector3(e, 0, 0.5 * (g.z_cfa_bot + g.z_cfa_top) - g.zc),
                    material=grid))
                geom.append(mp.Block(
                    size=mp.Vector3(mp.inf, args.cfa_grid_width, args.t_cfa),
                    center=mp.Vector3(0, e, 0.5 * (g.z_cfa_bot + g.z_cfa_top) - g.zc),
                    material=grid))
        # on-chip IR-cut filter: transparent here, only its thickness and index
        # matter for the geometric kernel (its spectral action is applied later)
        if args.t_ircf > 0:
            geom.append(mp.Block(
                size=mp.Vector3(mp.inf, mp.inf, args.t_ircf),
                center=mp.Vector3(0, 0, 0.5 * (g.z_cfa_top + g.z_ircf_top) - g.zc),
                material=mp.Medium(index=args.n_ircf)))
        geom.append(mp.Block(size=mp.Vector3(mp.inf, mp.inf, args.d_arc),
                             center=mp.Vector3(0, 0, 0.5 * args.d_arc - g.zc),
                             material=arc))
        geom.append(mp.Block(
            size=mp.Vector3(mp.inf, mp.inf, args.si_thickness + g.dpml),
            center=mp.Vector3(0, 0, -(args.si_thickness + g.dpml) / 2 - g.zc),
            material=si))
        # DTI: a real dielectric trench -- FDTD gets its reflection right,
        # which is exactly what the BPM cannot do.
        if args.dti_depth > 0:
            dti = mp.Medium(index=args.dti_index)
            for k in range(n + 1):
                e = (k - n / 2.0) * args.pitch
                geom.append(mp.Block(
                    size=mp.Vector3(args.dti_width, mp.inf, args.dti_depth),
                    center=mp.Vector3(e, 0, -args.dti_depth / 2 - g.zc),
                    material=dti))
                geom.append(mp.Block(
                    size=mp.Vector3(mp.inf, args.dti_width, args.dti_depth),
                    center=mp.Vector3(0, e, -args.dti_depth / 2 - g.zc),
                    material=dti))

    sources = [mp.Source(mp.GaussianSource(fcen, fwidth=args.fwidth * fcen),
                         component=mp.Ex,
                         center=mp.Vector3(0, 0, g.src_z - g.zc),
                         size=mp.Vector3(g.sx, g.sy, 0))]
    kx = np.sin(np.deg2rad(args.cra)) * fcen
    # A normally incident, x-polarised plane wave on a 4-fold symmetric stack is
    # even in x and y; Meep's Mirror already flips the vector component, so Ex
    # needs phase -1 across the x plane.  This cuts cost by 4.
    syms = []
    if args.symmetry and args.cra == 0.0 and args.ml_shift == 0.0:
        syms = [mp.Mirror(mp.X, phase=-1), mp.Mirror(mp.Y, phase=+1)]
    sim = mp.Simulation(cell_size=mp.Vector3(g.sx, g.sy, g.sz),
                        geometry=geom,
                        sources=sources,
                        resolution=args.resolution,
                        boundary_layers=[mp.PML(g.dpml, direction=mp.Z)],
                        k_point=mp.Vector3(kx, 0, 0),
                        default_material=mp.air,
                        force_complex_fields=(args.cra != 0.0),
                        symmetries=syms)
    return sim, g, dict(fcen=fcen, n_si=n_si, k_si=k_si)


def incident_power(args):
    """Downward power the source delivers at fcen, measured in vacuum.

    This must use the SAME machinery as the absorbed power (DFT fields), not
    add_flux: Meep's flux normalisation differs from 0.5*|E_dft|^2 by about a
    factor of two, which would scale every QE by that factor.  In vacuum a
    downward plane wave of DFT amplitude E carries 0.5*|E|^2 per unit area
    (c = eps0 = mu0 = 1 in Meep units).
    """
    sim, g, m = build(args, vacuum=True)
    pvol = mp.Volume(center=mp.Vector3(0, 0, -g.zc),            # Si surface plane
                     size=mp.Vector3(g.sx, g.sy, 0))
    pdft = sim.add_dft_fields([mp.Ex, mp.Ey, mp.Ez], m["fcen"], 0, 1, where=pvol)
    sim.run(until_after_sources=60)
    E2 = sum(np.abs(sim.get_dft_array(pdft, c, 0)) ** 2
             for c in (mp.Ex, mp.Ey, mp.Ez))
    _, _, _, w = sim.get_array_metadata(vol=pvol)
    return 0.5 * float((E2 * np.asarray(w).reshape(E2.shape)).sum()), sim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wavelength", type=float, default=550.0)
    ap.add_argument("--resolution", type=int, default=30, help="pixels per um")
    ap.add_argument("--cell-pixels", type=int, default=3)
    ap.add_argument("--aperture", choices=["center", "all"], default="center")
    ap.add_argument("--pitch", type=float, default=0.80)
    ap.add_argument("--ml-sag", type=float, default=0.35)
    ap.add_argument("--ml-roc", type=float, default=None,
                    help="override; default is derived from --ml-sag")
    ap.add_argument("--ml-shift", type=float, default=0.0)
    ap.add_argument("--t-ml-to-cfa", type=float, default=0.05)
    ap.add_argument("--t-cfa", type=float, default=0.50)
    ap.add_argument("--t-cfa-to-si", type=float, default=0.10)
    ap.add_argument("--t-ircf", type=float, default=0.0,
                    help="on-chip IR-cut thickness (above the colour filter)")
    ap.add_argument("--n-ircf", type=float, default=1.65)
    ap.add_argument("--cfa-grid-width", type=float, default=0.0,
                    help="low-index grid width between CFA cells (0 = none)")
    ap.add_argument("--n-cfa-grid", type=float, default=1.25)
    ap.add_argument("--d-arc", type=float, default=0.0688)
    ap.add_argument("--si-thickness", type=float, default=3.0)
    ap.add_argument("--dti-depth", type=float, default=2.6)
    ap.add_argument("--dti-width", type=float, default=0.10)
    ap.add_argument("--dti-index", type=float, default=1.46)
    ap.add_argument("--cra", type=float, default=0.0)
    ap.add_argument("--fwidth", type=float, default=0.15)
    ap.add_argument("--decay", type=float, default=1e-5)
    ap.add_argument("--incident-power", type=float, default=None,
                    help="reuse a vacuum-reference power for identical cell/source geometry")
    ap.add_argument("--out-dx-nm", type=float, default=50.0,
                    help="lateral grid of the exported G (match bxsim)")
    ap.add_argument("--out-dz-nm", type=float, default=50.0)
    ap.add_argument("--symmetry", type=int, default=1,
                    help="use mirror symmetry (normal incidence only)")
    ap.add_argument("--tag", type=str, default="")
    args = ap.parse_args()

    t0 = time.time()
    g = geometry_of(args)
    if mp.am_master():
        print("cell %.2f x %.2f x %.2f um at resolution %d  (%.1f Mvoxels)"
              % (g.sx, g.sy, g.sz, args.resolution,
                 g.sx * g.sy * g.sz * args.resolution ** 3 / 1e6))
        print("microlens sag %.2f um -> ROC %.2f um" % (args.ml_sag, ml_roc(args)))

    if args.incident_power is None:
        p_inc, _ = incident_power(args)
    else:
        p_inc = args.incident_power
    if mp.am_master():
        print("incident power (vacuum reference) = %.4g   [%.0f s]"
              % (p_inc, time.time() - t0))

    sim, g, m = build(args)
    vol = mp.Volume(center=mp.Vector3(0, 0, -args.si_thickness / 2 - g.zc),
                    size=mp.Vector3(g.sx, g.sy, args.si_thickness))
    dft = sim.add_dft_fields([mp.Ex, mp.Ey, mp.Ez], m["fcen"], 0, 1, where=vol)
    sim.run(until_after_sources=mp.stop_when_fields_decayed(
        20, mp.Ex, mp.Vector3(0, 0, -args.si_thickness / 2 - g.zc), args.decay))

    E2 = sum(np.abs(sim.get_dft_array(dft, c, 0)) ** 2
             for c in (mp.Ex, mp.Ey, mp.Ez))
    eps2 = 2 * m["n_si"] * m["k_si"]
    P = 0.5 * (2 * np.pi * m["fcen"]) * eps2 * E2      # absorbed power density
    # Meep's array slice is not simply cell/resolution: ask for the real
    # coordinates and the integration weights that go with them.
    xs, ys, zs, w = sim.get_array_metadata(vol=vol)
    xs, ys, zs = np.asarray(xs), np.asarray(ys), np.asarray(zs)
    if not mp.am_master():
        return
    assert P.shape == (xs.size, ys.size, zs.size), (P.shape, xs.size, ys.size, zs.size)

    n = args.cell_pixels
    ix = np.clip(((xs + g.sx / 2) / args.pitch).astype(int), 0, n - 1)
    iy = np.clip(((ys + g.sy / 2) / args.pitch).astype(int), 0, n - 1)
    Pw = P * np.asarray(w).reshape(P.shape)            # absorbed power per sample
    per_pixel = np.zeros((n, n))
    for a in range(n):
        for b in range(n):
            per_pixel[b, a] = Pw[np.ix_(ix == a, iy == b)].sum()
    # ``p_inc`` is integrated over the complete n x n source plane.  With a
    # centre-only clear CFA, only one pixel area reaches Si, so normalise by
    # p_inc/n**2.  With every CFA cell clear, the absorbed sum also covers the
    # full n x n plane and must instead be normalised by p_inc.
    p_norm = p_inc / (n * n) if args.aperture == "center" else p_inc
    qe_cell = per_pixel.sum() / p_norm
    split_raw = per_pixel / per_pixel.sum()
    # The source is linearly polarised along x, but the square lattice is
    # 4-fold symmetric, so the unpolarised answer is the average of the Ex run
    # and its 90-degree rotation, i.e. the transpose.  Mirror-symmetrising on
    # top of that removes discretisation asymmetry; what it removes is a
    # useful error bar, so report it.
    sym = 0.5 * (split_raw + split_raw.T)
    split = 0.25 * (sym + sym[::-1, :] + sym[:, ::-1] + sym[::-1, ::-1])
    asym = float(np.abs(split_raw - split).max())

    np.set_printoptions(precision=4, suppress=True)
    print("\nabsorbed-power split over the %dx%d block (rows = y, cols = x):" % (n, n))
    print("raw (Ex polarised):")
    print(split_raw)
    print("symmetrised (unpolarised); max deviation from raw = %.4f" % asym)
    print(split)
    c = n // 2
    print("own-pixel share = %.3f %%   crosstalk = %.3f %%"
          % (split[c, c] * 100, (1 - split[c, c]) * 100))
    print("total QE (absorbed / incident on illuminated area) = %.3f %%" % (qe_cell * 100))
    print("elapsed %.0f s" % (time.time() - t0))

    # ---- resample onto the bxsim diffusion grid: (nz, ny, nx), z from the
    # back surface downwards, values = absorbed fraction per grid cell.
    from scipy.interpolate import RegularGridInterpolator
    dx = args.out_dx_nm * 1e-3
    dz = args.out_dz_nm * 1e-3
    gx = (np.arange(round(g.sx / dx)) + 0.5) * dx - g.sx / 2
    gz_depth = (np.arange(round(args.si_thickness / dz)) + 0.5) * dz
    gz = -gz_depth                                     # z = 0 at the Si surface
    itp = RegularGridInterpolator((xs, ys, zs + g.zc), P, bounds_error=False,
                                  fill_value=None)
    GX, GY, GZ = np.meshgrid(gx, gx, gz, indexing="ij")
    Gd = itp(np.stack([GX, GY, GZ], axis=-1))          # power density
    Gd = np.maximum(Gd, 0.0) * (dx * dx * dz)          # -> per cell
    Gd *= Pw.sum() / Gd.sum()                          # keep the exact integral
    G = np.transpose(Gd, (2, 1, 0)) / p_norm

    out = pathlib.Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    f = out / ("fdtd_%dnm_%s%s.npz" % (args.wavelength, args.aperture,
                                       ("_" + args.tag) if args.tag else ""))
    np.savez(f, G=G, split=split, split_raw=split_raw, asym=asym, qe=qe_cell,
             per_pixel=per_pixel, incident_power=p_inc, args=vars(args), meta=m)
    print("wrote %s   (G shape %s, sum %.4f)" % (f, G.shape, G.sum()))


if __name__ == "__main__":
    main()
