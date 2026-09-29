"""Minority-carrier transport -> per-photodiode collection maps.

Instead of solving the continuity equation once per illumination condition,
we solve its *adjoint* once per geometry.  Let

    D grad^2 n - n/tau + G = 0,     n = 0 inside every photodiode collector,
                                    D dn/dnu + S n = 0 on recombining surfaces

and let J_c be the charge collected by photodiode c.  Define u_c by

    D grad^2 u - u/tau = 0,   u = 1 in PD_c, u = 0 in all other PDs,
                              D du/dnu + S u = 0 on recombining surfaces.

Green's identity then gives exactly

    J_c = integral of G * u_c dV,

i.e. u_c(x,y,z) is the probability that a carrier generated at (x,y,z) is
collected by photodiode c.  Because the array is periodic, u for any other
photodiode is a lateral shift of u for the center one, so ONE linear solve
serves every wavelength, incidence angle and CFA color.

The photodiode is modelled as a *volume* (its depleted region), not as a point
contact on the front surface: any carrier that reaches the depletion edge is
swept in by the built-in field.  That volume is what makes back-side DTI depth
matter -- if the trench overlaps the depletion region the pixel is electrically
isolated; if it stops short there is an open diffusion path to the neighbours.
"""
from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from .stack import PixelStack


def pd_footprint(stack: PixelStack, x, y, center_only: bool = False):
    X, Y = np.meshgrid(x, y)
    h = stack.pd_fill * stack.pitch_um / 2
    if center_only:
        return (np.abs(X) <= h) & (np.abs(Y) <= h)
    xl, yl = stack.cell_local(X, Y)
    return (np.abs(xl) <= h) & (np.abs(yl) <= h)


def dirichlet_volume(stack: PixelStack):
    """(nz, ny, nx) array: NaN where u is unknown, else the imposed value."""
    x, y, z, dx, dz = stack.diff_grid()
    nz = len(z)
    n_pd = max(1, int(round(stack.pd_depth_um / dz)))
    any_pd = pd_footprint(stack, x, y)
    ctr_pd = pd_footprint(stack, x, y, center_only=True)
    val = np.full((nz, len(y), len(x)), np.nan)
    lay = np.where(ctr_pd, 1.0, np.where(any_pd, 0.0, np.nan))
    val[nz - n_pd:] = lay
    return val


def collection_map(stack: PixelStack, rtol: float = 1e-10, verbose: bool = False):
    """Solve the adjoint problem; return u with shape (nz, ny, nx)."""
    x, y, z, dx, dz = stack.diff_grid()
    nx, ny, nz = len(x), len(y), len(z)
    D = stack.diff_coeff_cm2s * 1e8            # um^2/s
    tau = stack.lifetime_us * 1e-6             # s
    Sb = stack.s_back_cm_s * 1e4               # um/s
    Sf = stack.s_front_cm_s * 1e4

    A_lat = dx * dz                            # area of a lateral face
    A_z = dx * dx
    V = dx * dx * dz
    g_lat = D * A_lat / dx
    g_z = D * A_z / dz

    dval = dirichlet_volume(stack)
    fixed = ~np.isnan(dval)

    # lateral faces cut by a trench: face f_x[i] sits between column i and i+1
    npix_cells = int(round(stack.pitch_um / dx))
    f_x = np.zeros(nx, bool)
    if stack.dti_enabled:
        f_x[(np.arange(nx) + 1) % npix_cells == 0] = True
    n_dti = int(round(stack.dti_depth_um / dz)) if stack.dti_enabled else 0

    idx = lambda iz, iy, ix: (iz * ny + iy) * nx + ix
    N = nx * ny * nz
    rows, cols, vals = [], [], []
    b = np.zeros(N)
    ap = rows.append, cols.append, vals.append

    for iz in range(nz):
        blocked = iz < n_dti
        for iy in range(ny):
            for ix in range(nx):
                r = idx(iz, iy, ix)
                if fixed[iz, iy, ix]:
                    ap[0](r); ap[1](r); ap[2](1.0)
                    b[r] = dval[iz, iy, ix]
                    continue
                diag = -V / (D * tau)
                nbrs = []
                if not (blocked and f_x[ix]):
                    nbrs.append((idx(iz, iy, (ix + 1) % nx), g_lat, (iz, iy, (ix + 1) % nx)))
                if not (blocked and f_x[(ix - 1) % nx]):
                    nbrs.append((idx(iz, iy, (ix - 1) % nx), g_lat, (iz, iy, (ix - 1) % nx)))
                if not (blocked and f_x[iy]):
                    nbrs.append((idx(iz, (iy + 1) % ny, ix), g_lat, (iz, (iy + 1) % ny, ix)))
                if not (blocked and f_x[(iy - 1) % ny]):
                    nbrs.append((idx(iz, (iy - 1) % ny, ix), g_lat, (iz, (iy - 1) % ny, ix)))
                if iz == 0:
                    diag -= Sb * A_z                       # back-surface recombination
                else:
                    nbrs.append((idx(iz - 1, iy, ix), g_z, (iz - 1, iy, ix)))
                if iz == nz - 1:
                    diag -= Sf * A_z                       # front oxide interface
                else:
                    nbrs.append((idx(iz + 1, iy, ix), g_z, (iz + 1, iy, ix)))

                for c, g, key in nbrs:
                    diag -= g
                    if fixed[key]:
                        b[r] -= g * dval[key]              # keep the matrix symmetric
                    else:
                        ap[0](r); ap[1](c); ap[2](g)
                ap[0](r); ap[1](r); ap[2](diag)

    A = sp.csr_matrix(sp.coo_matrix((vals, (rows, cols)), shape=(N, N)))
    # rows of fixed cells are +1 on the diagonal, free rows are negative-definite
    sign = np.where(fixed.ravel(), 1.0, -1.0)
    A = sp.diags(sign) @ A
    b = sign * b
    diagA = A.diagonal()
    Minv = spla.LinearOperator((N, N), matvec=lambda v: v / diagA)
    u, info = spla.cg(A, b, rtol=rtol, atol=0.0, maxiter=20000, M=Minv)
    if verbose:
        print(f"  [diffusion] N={N}  cg info={info}  u in [{u.min():.3e}, {u.max():.3e}]")
    return u.reshape(nz, ny, nx)


def collect(G, u, stack: PixelStack, half: int | None = None):
    """Charge collected by each photodiode.

    Returns K[i+half, j+half] = charge collected by the photodiode at integer
    offset (i, j) (rows = y, cols = x) from the illuminated pixel.
    """
    n = int(round(stack.pitch_um / (stack.dx_diff_nm * 1e-3)))
    if half is None:
        half = stack.n_pix // 2
    K = np.zeros((2 * half + 1, 2 * half + 1))
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            K[i + half, j + half] = float((G * np.roll(u, (i * n, j * n),
                                                       axis=(1, 2))).sum())
    return K
