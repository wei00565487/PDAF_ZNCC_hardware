"""Draw the pixel structure that is actually being simulated.

Every dimension is read from the PixelStack object, so the drawing cannot
drift away from the model.  What the drawing shows that the numbers do not:

  * the on-chip IR-cut filter sits over R/G/B only, not over K.  Its thickness
    IS in the model (it raises the stack height), but its refractive index is
    taken as uniform across the array -- the lateral index step at an R/G/B to
    K boundary (OPD ~ lambda/10) is neglected;
  * the low-index grid inside the colour-filter layer is a real index step
    handled by a split-step BPM, unlike the DTI which is an absorbing wall;
  * the microlens is a spherical cap clipped to its own cell, so the modelled
    surface has a step at the cell boundary (a real gapless lens is smooth
    there).

Outputs: out/fig10_structure_3um.png, out/fig10_structure_0p8um.png
"""
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Polygon

from bxsim import PixelStack

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

CFA_COL = {"R": "#e2564a", "G": "#4fae55", "B": "#4a76e2", "K": "#2b2b2b"}
LAYER_COL = {
    "air": "#ffffff", "ml": "#f2c14e", "planar": "#dfe6ee", "ircf": "#9b6bd6",
    "cfa": None, "arc": "#7ad3c8", "si": "#8d99ae", "pd": "#5b6b8c",
    "dti": "#f0f0f0",
}

PATTERN = ["RGRG", "GBGB", "RGKK", "GBKK"]
BAYER = ["RG", "GB"]


def ml_profile(st, x):
    """Microlens top surface height above its base, as the model defines it.

    The model puts cell centres at x = 0, +-pitch (PixelStack.cell_local), while
    this drawing puts cell c over [c*pitch, (c+1)*pitch].  Shift by half a pitch
    so the lens apex lands on the pixel centre and the trench on the boundary --
    which is what the simulation actually does, and what a sensor without pupil
    correction looks like at CRA 0.
    """
    p = st.pitch_um
    xl = (x % p) - p / 2
    R = st.ml_roc_um
    sag = R - np.sqrt(np.maximum(R ** 2 - np.minimum(np.abs(xl), 0.999 * R) ** 2, 0))
    return st.ml_sag_um - sag


def top_view(ax, st, pattern, label_g=True):
    n = len(pattern)
    p = st.pitch_um
    for r in range(n):
        for c in range(n):
            col = pattern[r][c]
            ax.add_patch(Rectangle((c * p, (n - 1 - r) * p), p, p,
                                   facecolor=CFA_COL[col], edgecolor="none",
                                   alpha=0.85))
            ax.text((c + 0.5) * p, (n - 1 - r + 0.72) * p, col, ha="center",
                    va="center", fontsize=11, weight="bold",
                    color="w" if col == "K" else "#111")
            if label_g and col == "G":
                ax.text((c + 0.5) * p, (n - 1 - r + 0.30) * p, "(%d,%d)" % (r, c),
                        ha="center", va="center", fontsize=7.5, color="#111")
            # photodiode footprint
            h = st.pd_fill * p / 2
            ax.add_patch(Rectangle(((c + 0.5) * p - h, (n - 1 - r + 0.5) * p - h),
                                   2 * h, 2 * h, fill=False, ls=(0, (4, 2)),
                                   ec="#ffffff", lw=1.1))
            # microlens outline (cap clipped to the cell)
            th = np.linspace(0, 2 * np.pi, 80)
            a = min(p / 2, np.sqrt(max(st.ml_roc_um ** 2
                                       - (st.ml_roc_um - st.ml_sag_um) ** 2, 0)))
            ax.plot((c + 0.5) * p + a * np.cos(th),
                    (n - 1 - r + 0.5) * p + a * np.sin(th),
                    color="#333", lw=0.6, alpha=0.5)
    # DTI grid
    gw = st.cfa_grid_width_um if st.cfa_grid_enabled else 0.0
    for k in range(n + 1):
        if gw:                                   # low-index CFA grid
            ax.add_patch(Rectangle((k * p - gw / 2, 0), gw, n * p,
                                   facecolor="#e8e0f5", edgecolor="none", zorder=2))
            ax.add_patch(Rectangle((0, k * p - gw / 2), n * p, gw,
                                   facecolor="#e8e0f5", edgecolor="none", zorder=2))
        ax.add_patch(Rectangle((k * p - st.dti_width_um / 2, 0),
                               st.dti_width_um, n * p, facecolor="#ffffff",
                               edgecolor="#333", lw=0.4, zorder=3))
        ax.add_patch(Rectangle((0, k * p - st.dti_width_um / 2), n * p,
                               st.dti_width_um, facecolor="#ffffff",
                               edgecolor="#333", lw=0.4, zorder=3))
    ax.set_xlim(-0.35 * p, n * p + 0.35 * p)
    ax.set_ylim(-0.35 * p, n * p + 0.35 * p)
    ax.set_aspect("equal")
    ax.set_xlabel("x [um]")
    ax.set_ylabel("y [um]")
    ax.grid(False)
    # scale annotations
    ax.annotate("", xy=(0, -0.18 * p), xytext=(p, -0.18 * p),
                arrowprops=dict(arrowstyle="<->", lw=1.0))
    ax.text(p / 2, -0.30 * p, "pitch %.2f um" % p, ha="center", fontsize=8)
    ax.text(n * p + 0.05 * p, n * p * 0.52,
            "white dash = PD footprint\n(fill %.2f)\nthin circle = microlens\n"
            "white grid = DTI %.2f um" % (st.pd_fill, st.dti_width_um),
            fontsize=7, va="center")


def cross_section(ax, st, row, ircf_draw_um=0.0):
    """Cross-section along one CFA row.  z = 0 at the Si back surface, light
    arrives from +z (back-side illumination)."""
    n = len(row)
    p = st.pitch_um
    W = n * p
    z_arc = st.d_arc_um
    z_cfa_b = z_arc + st.t_cfa_to_si_um
    z_cfa_t = z_cfa_b + st.t_cfa_um
    z_ircf_t = z_cfa_t + ircf_draw_um
    z_ml_b = z_ircf_t + st.t_ml_to_cfa_um
    z_top = z_ml_b + st.ml_sag_um + 0.45 * p

    # silicon
    ax.add_patch(Rectangle((0, -st.si_thickness_um), W, st.si_thickness_um,
                           facecolor=LAYER_COL["si"], ec="none"))
    # depletion / collecting volume at the front side
    ax.add_patch(Rectangle((0, -st.si_thickness_um), W, st.pd_depth_um,
                           facecolor=LAYER_COL["pd"], ec="none", alpha=0.9))
    ax.axhline(-st.si_thickness_um + st.pd_depth_um, color="w", lw=0.9,
               ls=(0, (5, 3)))
    ax.text(W * 0.5, -st.si_thickness_um + st.pd_depth_um / 2,
            "photodiode depletion volume  (%.2f um, fill %.2f)"
            % (st.pd_depth_um, st.pd_fill),
            ha="center", va="center", fontsize=7.5, color="w")
    ax.text(W * 0.02, -st.pd_depth_um * 0.25 - 0.05 * st.si_thickness_um,
            "silicon  %.1f um" % st.si_thickness_um, fontsize=8, color="w")
    # DTI
    for k in range(n + 1):
        ax.add_patch(Rectangle((k * p - st.dti_width_um / 2,
                                -st.dti_depth_um), st.dti_width_um,
                               st.dti_depth_um, facecolor=LAYER_COL["dti"],
                               ec="#444", lw=0.4))
    # ARC
    ax.add_patch(Rectangle((0, 0), W, z_arc, facecolor=LAYER_COL["arc"], ec="none"))
    # planarisation between CFA and Si
    ax.add_patch(Rectangle((0, z_arc), W, st.t_cfa_to_si_um,
                           facecolor=LAYER_COL["planar"], ec="none"))
    # colour filter cells
    for c, col in enumerate(row):
        ax.add_patch(Rectangle((c * p, z_cfa_b), p, st.t_cfa_um,
                               facecolor=CFA_COL[col], ec="#555", lw=0.4,
                               alpha=0.85))
        ax.text((c + 0.5) * p, z_cfa_b + st.t_cfa_um / 2, col, ha="center",
                va="center", fontsize=10, weight="bold",
                color="w" if col == "K" else "#111")
        # low-index grid walls inside the colour-filter layer
        if st.cfa_grid_enabled:
            for e in (c * p, (c + 1) * p):
                ax.add_patch(Rectangle((e - st.cfa_grid_width_um / 2, z_cfa_b),
                                       st.cfa_grid_width_um, st.t_cfa_um,
                                       facecolor="#ffffff", ec="#555", lw=0.4,
                                       zorder=4))
        # on-chip IR-cut filter: over R/G/B only
        if col != "K" and ircf_draw_um > 0:
            ax.add_patch(Rectangle((c * p, z_cfa_t), p, ircf_draw_um,
                                   facecolor=LAYER_COL["ircf"], ec="#555",
                                   lw=0.4, alpha=0.8))
        elif col == "K" and ircf_draw_um > 0:
            ax.add_patch(Rectangle((c * p, z_cfa_t), p, ircf_draw_um,
                                   facecolor="none", ec="#555", lw=0.4,
                                   ls=(0, (2, 2))))
            ax.text((c + 0.5) * p, z_cfa_t + ircf_draw_um / 2, "no IR cut",
                    ha="center", va="center", fontsize=6.5, color="#555")
    # planarisation up to the microlens base
    ax.add_patch(Rectangle((0, z_ircf_t), W, st.t_ml_to_cfa_um,
                           facecolor=LAYER_COL["planar"], ec="none"))
    # microlenses
    xs = np.linspace(0, W, 1600)
    prof = ml_profile(st, xs)
    for c in range(n):
        m = (xs >= c * p) & (xs <= (c + 1) * p)
        pts = np.column_stack([np.r_[xs[m], xs[m][::-1]],
                               np.r_[z_ml_b + prof[m], np.full(m.sum(), z_ml_b)]])
        ax.add_patch(Polygon(pts, closed=True, facecolor=LAYER_COL["ml"],
                             ec="#8a6d1f", lw=0.6))

    # illumination arrows
    for c in range(n):
        ax.annotate("", xy=((c + 0.5) * p, z_ml_b + st.ml_sag_um + 0.02 * p),
                    xytext=((c + 0.5) * p, z_top),
                    arrowprops=dict(arrowstyle="-|>", lw=1.1, color="#c00"))
    ax.text(W * 0.5, z_top * 0.985, "back-side illumination", ha="center",
            va="top", fontsize=8, color="#c00")

    # layer labels on the right, on an evenly spaced ladder with leader lines
    lab = [(z_arc / 2, "ARC SiN %.1f nm" % (st.d_arc_um * 1000)),
           (z_arc + st.t_cfa_to_si_um / 2, "planarisation %.2f um" % st.t_cfa_to_si_um),
           (z_cfa_b + st.t_cfa_um / 2, "colour filter %.2f um" % st.t_cfa_um),
           (z_ircf_t + st.t_ml_to_cfa_um / 2,
            "planarisation %.2f um" % st.t_ml_to_cfa_um),
           (z_ml_b + st.ml_sag_um * 0.6,
            "microlens sag %.2f um (ROC %.2f um)" % (st.ml_sag_um, st.ml_roc_um))]
    if ircf_draw_um > 0:
        lab.insert(3, (z_cfa_t + ircf_draw_um / 2,
                       "on-chip IR cut, R/G/B only\n(zero thickness in the model)"))
    lab.append((-st.si_thickness_um + st.pd_depth_um / 2,
                "photodiode depletion %.2f um" % st.pd_depth_um))
    lab.append((-st.dti_depth_um / 2,
                "DTI depth %.2f um / width %.2f um"
                % (st.dti_depth_um, st.dti_width_um)))

    top = z_ml_b + st.ml_sag_um
    ys = np.linspace(top, -st.si_thickness_um * 0.95, len(lab))
    for (z, t), y in zip(lab, ys):
        ax.annotate(t, xy=(W, z), xytext=(W * 1.06, y), fontsize=7.5,
                    va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color="#777",
                                    shrinkA=0, shrinkB=2))

    # stack height bracket -- the quantity that drives optical crosstalk
    ax.annotate("", xy=(-0.012 * W, 0), xytext=(-0.012 * W, z_ml_b),
                arrowprops=dict(arrowstyle="<->", lw=1.4, color="#b30"))
    ax.text(-0.03 * W, z_ml_b / 2,
            "stack\nheight\n%.2f um" % st.stack_height_um,
            fontsize=7.5, color="#b30", ha="right", va="center")

    ax.set_xlim(-0.24 * W, W * 1.45)
    ax.set_ylim(-st.si_thickness_um * 1.04, z_top * 1.02)
    ax.set_aspect("equal")
    ax.set_xlabel("x [um]")
    ax.set_ylabel("z [um]   (0 = Si back surface)")
    ax.grid(False)


def figure(st, pattern, row, name, title, ircf_draw_um):
    fig = plt.figure(figsize=(14.5, 6.4))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.55])
    ax1 = fig.add_subplot(gs[0])
    top_view(ax1, st, pattern)
    ax1.set_title("top view -- %d x %d CFA cell" % (len(pattern), len(pattern)),
                  fontsize=10)
    ax2 = fig.add_subplot(gs[1])
    cross_section(ax2, st, row, ircf_draw_um)
    ax2.set_title("cross-section along the row \"%s\"  (to scale)" % row, fontsize=10)
    fig.suptitle(title, y=0.99, fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / name)
    plt.close(fig)
    print("wrote", OUT / name)


def main():
    st3 = PixelStack(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
                     pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0,
                     dti_width_um=0.20, ml_sag_um=0.80, t_ml_to_cfa_um=0.10,
                     t_cfa_um=0.90, t_cfa_to_si_um=0.20, t_ircf_um=0.30,
                     cfa_grid_enabled=True, cfa_grid_width_um=0.15)
    figure(st3, PATTERN, "RGKK", "fig10_structure_3um.png",
           "Simulated structure: 3.0 um pitch, 6.0 um Si, full-depth DTI, "
           "3.0 um depletion, 100 % aperture, 0.30 um on-chip IR cut, "
           "low-index CFA grid  (RGB-IR 4x4)",
           ircf_draw_um=st3.t_ircf_um)

    st08 = PixelStack(pitch_um=0.80, n_pix=3, si_thickness_um=3.0, pd_depth_um=1.0,
                      pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True,
                      dti_depth_um=3.0, t_ircf_um=0.30, cfa_grid_enabled=True,
                      cfa_grid_width_um=0.10)
    figure(st08, PATTERN, "RGKK", "fig10_structure_0p8um.png",
           "Simulated structure: 0.8 um pitch, 3.0 um Si, full-depth DTI, "
           "1.0 um depletion, 75 % aperture, 0.30 um on-chip IR cut, "
           "low-index CFA grid  (RGB-IR 4x4)",
           ircf_draw_um=st08.t_ircf_um)


if __name__ == "__main__":
    main()
