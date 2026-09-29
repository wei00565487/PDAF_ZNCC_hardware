"""Small plotting helpers (matplotlib only)."""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 130, "savefig.dpi": 130, "font.size": 9,
    "axes.grid": True, "grid.alpha": 0.25, "axes.titlesize": 10,
    "figure.facecolor": "white", "savefig.bbox": "tight",
})

BAYER_COLORS = {"R": "#d62728", "Gr": "#2ca02c", "Gb": "#7fbf7f", "B": "#1f77b4"}


def kernel_heatmap(ax, K, title="", fmt="{:.3f}", vmax=None, log=False):
    Kp = K / K.sum()
    if log:
        im = ax.imshow(np.log10(np.maximum(Kp, 1e-6)), cmap="magma", vmin=-5, vmax=0)
    else:
        im = ax.imshow(Kp, cmap="magma", vmin=0, vmax=vmax or Kp.max())
    h = K.shape[0] // 2
    for i in range(K.shape[0]):
        for j in range(K.shape[1]):
            ax.text(j, i, fmt.format(Kp[i, j] * 100), ha="center", va="center",
                    fontsize=6.5, color="w" if Kp[i, j] < 0.5 * Kp.max() else "k")
    ax.set_xticks(range(K.shape[1]), [str(v - h) for v in range(K.shape[1])])
    ax.set_yticks(range(K.shape[0]), [str(v - h) for v in range(K.shape[0])])
    ax.set_title(title)
    ax.grid(False)
    return im


def section_xz(ax, G, stack, title="", log=True, ylabel=True):
    """x-z cross-section of the generation cube through the array center."""
    iy = G.shape[1] // 2
    S = G[:, iy, :]
    span = stack.span_um
    ext = [-span / 2, span / 2, stack.si_thickness_um, 0.0]
    if log:
        S = np.log10(np.maximum(S / S.max(), 1e-5))
        im = ax.imshow(S, extent=ext, aspect="auto", cmap="inferno", vmin=-5, vmax=0)
    else:
        im = ax.imshow(S, extent=ext, aspect="auto", cmap="inferno")
    for k in range(stack.n_pix + 1):
        ax.axvline(-span / 2 + k * stack.pitch_um, color="cyan", lw=0.5, alpha=0.6)
    if stack.dti_enabled:
        ax.axhline(stack.dti_depth_um, color="lime", lw=0.8, ls="--")
    ax.axhline(stack.si_thickness_um - stack.pd_depth_um, color="w", lw=0.8, ls=":")
    ax.set_xlabel("x [um]")
    if ylabel:
        ax.set_ylabel("depth in Si [um]")
    ax.set_title(title); ax.grid(False)
    return im
