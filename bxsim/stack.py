"""Geometry / material description of one Bayer pixel stack (BSI)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import materials as M


@dataclass
class PixelStack:
    """Back-side-illuminated Bayer pixel.

    z is measured from the Si back surface (illuminated side, z=0) towards the
    front side where the photodiode collector sits (z = si_thickness_um).
    Light path: microlens -> planarization -> CFA -> ARC -> Si.
    """

    # --- lateral ---------------------------------------------------------
    pitch_um: float = 0.80
    n_pix: int = 5                      # simulated array size (odd), periodic

    # --- microlens -------------------------------------------------------
    ml_sag_um: float = 0.35             # physical height of the spherical cap
    ml_aperture_frac: float = 1.0       # 1.0 = gapless microlens
    n_ml: float = M.N_MICROLENS         # microlens resin
    n_above: float = 1.0                # air on top of the microlens
    n_planar: float = M.N_PLANAR
    ml_roc_override_um: float | None = None
    ml_shift_um: float = 0.0            # lens shift for CRA compensation
    ml_shift_az_deg: float = 0.0        # direction of the shift

    # --- layer thicknesses ----------------------------------------------
    t_ml_to_cfa_um: float = 0.05
    t_ircf_um: float = 0.0              # on-chip IR-cut filter over R/G/B
    n_ircf: float = 1.65
    t_cfa_um: float = 0.50
    t_k_cfa_um: float | None = None     # optional total thickness of a K/IR CFA stack
    t_cfa_to_si_um: float = 0.10
    cfa_aperture_frac: float = 1.0      # CFA cell opening (1.0 = butted)

    # --- low-index grid between the colour filter cells ------------------
    cfa_grid_enabled: bool = False
    cfa_grid_width_um: float = 0.15
    n_cfa_grid: float = 1.25            # low-index resin / air-gap wall
    cfa_grid_steps: int = 20            # split-step slices through the CFA
    cfa_grid_edge_um: float = 0.05      # sidewall transition width

    # --- silicon ---------------------------------------------------------
    si_thickness_um: float = 3.00
    d_arc_um: float = 0.0688

    # --- deep trench isolation ------------------------------------------
    dti_enabled: bool = True
    dti_depth_um: float = 2.6           # etched from the back surface (z=0)
    dti_width_um: float = 0.10
    dti_blocks_light: bool = True       # metal/absorbing fill (see README caveat)

    # --- photodiode / transport -----------------------------------------
    pd_fill: float = 0.75               # PD footprint / pitch (linear)
    pd_depth_um: float = 1.00           # depth of the collecting (depleted) volume,
                                        # measured up from the front surface
    diff_coeff_cm2s: float = 25.0       # electron D in lightly doped p-epi
    lifetime_us: float = 10.0
    s_back_cm_s: float = 200.0          # passivated back surface
    s_front_cm_s: float = 0.0           # non-PD front surface (STI/oxide)

    # --- numerics --------------------------------------------------------
    dx_opt_nm: float = 25.0
    dz_opt_nm: float = 25.0
    dx_diff_nm: float = 50.0
    dz_diff_nm: float = 50.0

    def __post_init__(self):
        if self.n_pix % 2 == 0:
            raise ValueError("n_pix must be odd so that a center pixel exists")

    # ------------------------------------------------------------------
    @property
    def span_um(self) -> float:
        return self.n_pix * self.pitch_um

    @property
    def stack_height_um(self) -> float:
        """Microlens plane -> Si surface, geometric distance."""
        return (self.t_ml_to_cfa_um + self.t_ircf_um + self.t_cfa_um
                + self.t_cfa_to_si_um)

    def stack_height_for(self, source_color: str | None = None) -> float:
        """Optical stack height for a selected source CFA cell.

        ``t_k_cfa_um`` represents the full filter thickness over a K/IR cell.
        K has no RGB on-chip IR-cut layer, so that layer is replaced by the K
        stack rather than added to it.  With the default ``None``, every source
        uses the legacy uniform geometry.
        """
        if source_color is not None and source_color.upper() == "K" \
                and self.t_k_cfa_um is not None:
            return self.t_ml_to_cfa_um + self.t_k_cfa_um + self.t_cfa_to_si_um
        return self.stack_height_um

    @property
    def ml_roc_um(self) -> float:
        """Radius of curvature of a gapless spherical cap of height `ml_sag_um`.

        The cap must cover the square cell, so its base radius is the pixel
        half-diagonal.
        """
        if self.ml_roc_override_um is not None:
            return self.ml_roc_override_um
        a = self.ml_aperture_frac * self.pitch_um / np.sqrt(2.0)
        h = self.ml_sag_um
        return (a * a + h * h) / (2 * h)

    @property
    def ml_focus_um(self) -> float:
        """Paraxial focal distance measured from the microlens, inside the stack."""
        return self.ml_roc_um * self.n_planar / (self.n_ml - self.n_above)

    def opt_grid(self):
        """(x, y) cell-center coordinates of the optical grid, centered on 0."""
        dx = self.dx_opt_nm * 1e-3
        n = int(round(self.span_um / dx))
        x = (np.arange(n) + 0.5) * dx - self.span_um / 2
        return x, x, dx

    def diff_grid(self):
        dx = self.dx_diff_nm * 1e-3
        dz = self.dz_diff_nm * 1e-3
        nx = int(round(self.span_um / dx))
        nz = int(round(self.si_thickness_um / dz))
        x = (np.arange(nx) + 0.5) * dx - self.span_um / 2
        z = (np.arange(nz) + 0.5) * dz
        return x, x, z, dx, dz

    # ------------------------------------------------------------------
    def cell_local(self, x, y):
        """Coordinates relative to the center of the enclosing pixel cell."""
        p = self.pitch_um
        xl = ((x + p / 2) % p) - p / 2
        yl = ((y + p / 2) % p) - p / 2
        return xl, yl

    def cfa_grid_index(self, x, y):
        """Lateral refractive-index map of the colour-filter layer.

        The low-index wall sits on the cell boundary and confines light inside
        its own filter cell by total internal reflection.  Unlike the DTI this
        is a modest index step, so a split-step BPM handles it correctly --
        guiding is exactly what BPM is for.
        """
        X, Y = np.meshgrid(x, y)
        n = np.full(X.shape, M.N_CFA)
        if not self.cfa_grid_enabled:
            return n
        xl, yl = self.cell_local(X, Y)
        half = self.pitch_um / 2 - self.cfa_grid_width_um / 2
        e = max(self.cfa_grid_edge_um, 1e-6)
        # a smooth sidewall: a perfectly sharp index step throws power into
        # evanescent orders that a one-way BPM simply loses
        w = np.maximum(0.5 * (1 + np.tanh((np.abs(xl) - half) / e)),
                       0.5 * (1 + np.tanh((np.abs(yl) - half) / e)))
        return M.N_CFA + (self.n_cfa_grid - M.N_CFA) * w

    def dti_mask_xy(self, x, y):
        """1 inside silicon, 0 inside a trench (lateral footprint)."""
        if not self.dti_enabled:
            return np.ones((len(y), len(x)))
        X, Y = np.meshgrid(x, y)
        xl, yl = self.cell_local(X, Y)
        half = self.pitch_um / 2 - self.dti_width_um / 2
        return ((np.abs(xl) < half) & (np.abs(yl) < half)).astype(float)

    def bayer_color(self, i: int, j: int, pattern: str = "RGGB") -> str:
        """Color of the pixel at integer offset (i, j) from the center pixel.

        The center pixel (0,0) is taken to be the first letter of `pattern`.
        """
        p = pattern.upper()
        return p[(i % 2) * 2 + (j % 2)]
