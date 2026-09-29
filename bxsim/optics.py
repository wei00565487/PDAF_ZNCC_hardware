"""Scalar wave propagation through the pixel stack (angular-spectrum BPM).

The field is propagated plane-to-plane with the exact angular spectrum
transfer function, so it is a diffraction-correct model (not ray tracing) and
is valid for sub-micron pitches where the microlens f/# is small.

Limitations (documented in README):
  * scalar / no polarization, no vector focusing effects,
  * no back-reflections inside the stack (one-way BPM),
  * DTI is modelled as an absorbing wall, not a reflecting oxide trench.
Use the Meep FDTD script in `meep/` when those matter.
"""
from __future__ import annotations

import numpy as np

from . import materials as M
from .stack import PixelStack


def _angular_spectrum(U, dz_um, wl_um, n_complex, dx_um):
    """One-way propagation over dz in a homogeneous (possibly lossy) medium."""
    ny, nx = U.shape
    fx = np.fft.fftfreq(nx, d=dx_um)
    fy = np.fft.fftfreq(ny, d=dx_um)
    KX, KY = np.meshgrid(2 * np.pi * fx, 2 * np.pi * fy)
    k = 2 * np.pi * n_complex / wl_um
    kz = np.sqrt(k ** 2 - KX ** 2 - KY ** 2 + 0j)
    kz = np.where(kz.imag < 0, -kz, kz)          # decaying branch
    return np.fft.ifft2(np.fft.fft2(U) * np.exp(1j * kz * dz_um))


def microlens_phase(stack: PixelStack, x, y, wl_um):
    """Thin-element phase of a gapless spherical microlens array."""
    X, Y = np.meshgrid(x, y)
    az = np.deg2rad(stack.ml_shift_az_deg)
    xl, yl = stack.cell_local(X - stack.ml_shift_um * np.cos(az),
                              Y - stack.ml_shift_um * np.sin(az))
    r = np.hypot(xl, yl)
    R = stack.ml_roc_um
    sag = R - np.sqrt(np.maximum(R ** 2 - np.minimum(r, 0.999 * R) ** 2, 0.0))
    k0 = 2 * np.pi / wl_um
    phase = -k0 * (stack.n_ml - stack.n_above) * sag
    amp = np.ones_like(sag)
    if stack.ml_aperture_frac < 1.0:
        h = stack.pitch_um * stack.ml_aperture_frac / 2
        amp = ((np.abs(xl) <= h) & (np.abs(yl) <= h)).astype(float)
    return amp * np.exp(1j * phase)


def cfa_aperture(stack: PixelStack, x, y, which="center"):
    """Amplitude mask selecting which CFA cell(s) transmit."""
    X, Y = np.meshgrid(x, y)
    if which == "all":
        base = np.ones_like(X)
    else:
        h = stack.pitch_um / 2
        base = ((np.abs(X) < h) & (np.abs(Y) < h)).astype(float)
    if stack.cfa_aperture_frac < 1.0:
        xl, yl = stack.cell_local(X, Y)
        h2 = stack.pitch_um * stack.cfa_aperture_frac / 2
        base = base * ((np.abs(xl) <= h2) & (np.abs(yl) <= h2))
    return base


def fnumber_directions(f_number: float, cra_deg: float = 0.0,
                       azimuth_deg: float = 0.0, n: int = 32):
    """Direction cosines sampling the cone that an f/N lens delivers.

    NA = 1 / (2 N), so the marginal ray sits at asin(NA) from the chief ray.
    For a uniformly bright exit pupil the power per unit area from direction
    (theta, phi) goes as L*cos(theta)*dOmega = L*du*dv, i.e. the weight is
    UNIFORM in the direction-cosine plane -- so a uniform disk sampling with
    equal weights is the correct quadrature.  A Fibonacci (sunflower) lattice
    is used because it fills the disk evenly at any n.
    """
    na = 1.0 / (2.0 * f_number)
    i = np.arange(n) + 0.5
    r = na * np.sqrt(i / n)
    th = i * np.pi * (3.0 - np.sqrt(5.0))
    u, v = r * np.cos(th), r * np.sin(th)
    az = np.deg2rad(azimuth_deg)
    u0 = np.sin(np.deg2rad(cra_deg)) * np.cos(az)
    v0 = np.sin(np.deg2rad(cra_deg)) * np.sin(az)
    return np.stack([u + u0, v + v0], axis=1)


def generation_cone(stack: PixelStack, wl_nm: float, f_number: float,
                    cra_deg: float = 0.0, azimuth_deg: float = 0.0,
                    aperture: str = "center", n_samples: int = 32,
                    source_color: str | None = None):
    """Generation profile under f/N illumination.

    Under a flat field the exit pupil behaves as an incoherent extended source
    (van Cittert-Zernike), so the plane-wave components are mutually incoherent
    and their *intensities* add.  For a point-source PSF the pupil is coherent
    instead and the fields would have to be added -- this function is the
    flat-field / QE / crosstalk case.
    """
    dirs = fnumber_directions(f_number, cra_deg, azimuth_deg, n_samples)
    G = None
    for u, v in dirs:
        g = generation(stack, wl_nm, aperture=aperture, uv=(u, v),
                       source_color=source_color)
        G = g if G is None else G + g
    return G / len(dirs)


def generation(stack: PixelStack, wl_nm: float, cra_deg: float = 0.0,
               azimuth_deg: float = 0.0, aperture: str = "center",
               return_fields: bool = False, uv=None,
               source_color: str | None = None):
    """Photo-carrier generation profile inside silicon.

    Returns G with shape (nz, ny, nx) in units of "absorbed photons per grid
    cell per photon incident on one pixel area", i.e. sum(G) <= 1 for
    aperture='center'.
    """
    x, y, dx = stack.opt_grid()
    wl_um = wl_nm * 1e-3
    k0 = 2 * np.pi / wl_um

    # --- incident plane wave (direction cosines in air; k_transverse conserved)
    X, Y = np.meshgrid(x, y)
    if uv is None:
        th, az = np.deg2rad(cra_deg), np.deg2rad(azimuth_deg)
        u, v = np.sin(th) * np.cos(az), np.sin(th) * np.sin(az)
    else:
        u, v = float(uv[0]), float(uv[1])
    U = np.exp(1j * k0 * (u * X + v * Y)).astype(complex)

    # --- microlens
    U = U * microlens_phase(stack, x, y, wl_um)

    # --- planarization -> CFA plane
    U = _angular_spectrum(U, stack.t_ml_to_cfa_um, wl_um, stack.n_planar, dx)

    is_k_stack = (source_color is not None and source_color.upper() == "K"
                  and stack.t_k_cfa_um is not None)

    # --- on-chip IR-cut filter (its spectral action is applied later, as part
    # of the per-cell transmittance; here only its physical thickness matters,
    # because it pushes the colour filter further from the silicon)
    # A configured K stack replaces this RGB-only layer.
    if stack.t_ircf_um > 0 and not is_k_stack:
        U = _angular_spectrum(U, stack.t_ircf_um, wl_um, stack.n_ircf, dx)

    # --- color filter (amplitude mask at entrance, then propagate through it)
    U = U * cfa_aperture(stack, x, y, aperture)
    cfa_thickness = stack.t_k_cfa_um if is_k_stack else stack.t_cfa_um
    if stack.cfa_grid_enabled:
        # split-step BPM: a phase screen for the lateral index map, then a
        # homogeneous propagation slice.  Phase screens are unitary, so this
        # conserves energy exactly.
        n_map = stack.cfa_grid_index(x, y)
        n_ref = float(n_map.mean())
        nz = max(1, int(stack.cfa_grid_steps))
        dz_c = cfa_thickness / nz
        screen = np.exp(1j * k0 * (n_map - n_ref) * dz_c)
        for _ in range(nz):
            U = U * screen
            U = _angular_spectrum(U, dz_c, wl_um, n_ref, dx)
    else:
        U = _angular_spectrum(U, cfa_thickness, wl_um, M.N_CFA, dx)

    # --- CFA -> Si surface
    U = _angular_spectrum(U, stack.t_cfa_to_si_um, wl_um, stack.n_planar, dx)

    # --- into silicon through the ARC
    # incidence angle at the ARC, inside the planarisation (n*sin(theta) is
    # conserved from air, where the direction cosines are defined)
    sin_p = min(np.hypot(u, v) / stack.n_planar, 0.999)
    T_arc = M.arc_transmittance(wl_nm, n_top=stack.n_planar, d_arc_um=stack.d_arc_um,
                                theta_deg=np.rad2deg(np.arcsin(sin_p)))
    U = U * np.sqrt(T_arc)

    n_si = M.si_index_complex(wl_nm)
    alpha = M.si_alpha_per_um(wl_nm)
    dz = stack.dz_opt_nm * 1e-3
    nz = int(round(stack.si_thickness_um / dz))
    mask = stack.dti_mask_xy(x, y) if (stack.dti_enabled and stack.dti_blocks_light) \
        else np.ones_like(X)
    n_dti = int(round(stack.dti_depth_um / dz))

    G = np.empty((nz, len(y), len(x)))
    for iz in range(nz):
        if iz < n_dti:
            U = U * mask                      # light eaten by the trench is not
        I = np.abs(U) ** 2                    # silicon absorption, so mask first
        p_in = I.sum()
        U = _angular_spectrum(U, dz, wl_um, n_si, dx)
        p_out = float((np.abs(U) ** 2).sum())
        # Absorbed power in this slab is exactly the power the (otherwise
        # unitary) propagator lost.  Using alpha*|E|^2 directly would undercount
        # oblique rays, whose path through the slab is dz/cos(theta) -- that is
        # where the ~1 % energy deficit came from.  Distribute the loss over the
        # slab in proportion to the local intensity.
        G[iz] = I * ((p_in - p_out) / p_in) if p_in > 0 else 0.0

    # normalize: incident photons on one pixel area = |U0|^2 * pitch^2
    G *= dx * dx / stack.pitch_um ** 2
    if return_fields:
        return G, U
    return G


def downsample(G, fx: int, fz: int):
    """Sum-pool a (nz, ny, nx) generation cube onto the diffusion grid."""
    nz, ny, nx = G.shape
    assert nz % fz == 0 and ny % fx == 0 and nx % fx == 0
    return (G.reshape(nz // fz, fz, ny // fx, fx, nx // fx, fx)
             .sum(axis=(1, 3, 5)))
