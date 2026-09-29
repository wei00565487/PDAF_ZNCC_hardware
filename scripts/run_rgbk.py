"""RGB-IR (4x4) pattern: the six green pixels are not equivalent.

Pattern (row 0 at the top, column 0 at the left):

        R G R G
        G B G B
        R G K K
        G B K K

K is a visible-cut / IR-pass cell.  The photodiodes are all identical, so the
crosstalk kernel is the same everywhere; what differs between the six G pixels
is *which colour filters sit around them*.  A G pixel with a K neighbour
receives no visible crosstalk from that side, so its visible response is lower
(and purer) than a G pixel surrounded by R/G/B.

    S_p(lambda) = sum_o  T_{pattern[p - o]}(lambda) * K_geom[o]

At an oblique chief ray the kernel is no longer symmetric, so it matters
whether the K cell is on the up-tilt or the down-tilt side of the G pixel.

Outputs: out/fig8_rgbk_G.png, out/rgbk_G.csv
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import PixelStack, Simulator, materials as M

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

WL = np.arange(400, 1001, 20.0)
CRAS = (0.0, 30.0)
PATTERN = ["RGRG",
           "GBGB",
           "RGKK",
           "GBKK"]
NP = len(PATTERN)

GEOMS = {
    "3.0um FDTI": dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
                       pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0,
                       dti_width_um=0.20, ml_sag_um=0.80, t_ml_to_cfa_um=0.10,
                       t_cfa_um=0.90, t_cfa_to_si_um=0.20, dx_opt_nm=50.0,
                       dz_opt_nm=50.0, dx_diff_nm=100.0, dz_diff_nm=100.0,
                       t_ircf_um=0.30, cfa_grid_enabled=True,
                       cfa_grid_width_um=0.15),
    "0.8um FDTI": dict(pitch_um=0.80, n_pix=3, si_thickness_um=3.0, pd_depth_um=1.0,
                       pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True,
                       dti_depth_um=3.0, t_ircf_um=0.30, cfa_grid_enabled=True,
                       cfa_grid_width_um=0.10),
}


# An on-chip IR-cut filter is deposited over the R/G/B cells only, so those
# pixels get NO direct IR: whatever IR they show up with has crossed over from
# a neighbouring K cell.  IRCF_LEAK is the residual transmittance of that
# filter in the NIR (a real interference stack has finite optical density);
# 0 is the ideal case.
IRCF_LEAK = 0.0

# Illumination: the cone an f/N taking lens delivers, not a plane wave.
F_NUMBER = 1.8
N_SAMPLES = 16


def transmittance(color, wl, ircf_leak=None):
    """CFA transmittance including the on-chip IR cut over R/G/B.

    NOTE: like the R/G/B curves, the K curve is an assumed shape, not measured
    data -- an IR-pass black resist with a ~780 nm cut-on, and no IR cut on top.
    """
    if color == "K":
        return 0.90 / (1.0 + np.exp(-(wl - 780.0) / 22.0))
    leak = IRCF_LEAK if ircf_leak is None else ircf_leak
    t = M.cfa_transmittance(wl, color, nir_leak=True)
    f = M.ircf_transmittance(wl) / 0.97          # 1 in the pass band, 0 in the NIR
    return t * np.maximum(f, leak)


def g_positions():
    return [(r, c) for r in range(NP) for c in range(NP) if PATTERN[r][c] == "G"]


def neighbours(pr, pc, half):
    """The colour of the CFA cell feeding each kernel offset."""
    out = {}
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            out[(i, j)] = PATTERN[(pr - i) % NP][(pc - j) % NP]
    return out


def response(sim, wl, cra, pr, pc, T):
    """QE(lambda) of the pixel at pattern position (pr, pc)."""
    s = np.zeros(len(wl))
    for k, w in enumerate(wl):
        K = sim.kernel(w, cra_deg=cra, f_number=F_NUMBER, n_samples=N_SAMPLES)
        half = K.shape[0] // 2
        nb = neighbours(pr, pc, half)
        s[k] = sum(T[nb[(i, j)]][k] * K[i + half, j + half]
                   for i in range(-half, half + 1)
                   for j in range(-half, half + 1))
    return s


def main():
    t0 = time.time()
    T = {c: transmittance(c, WL) for c in "RGBK"}
    gpos = g_positions()
    print("green pixels in the 4x4 cell:", gpos)

    rows = []
    fig, axes = plt.subplots(2, len(GEOMS), figsize=(6.6 * len(GEOMS), 7.6),
                             sharex=True)
    for col, (gname, kw) in enumerate(GEOMS.items()):
        sim = Simulator(PixelStack(**kw), verbose=False)
        for row, cra in enumerate(CRAS):
            ax = axes[row, col]
            # reference: a G pixel with zero spatial crosstalk
            K0 = sim.kernel(550.0, cra_deg=cra, f_number=F_NUMBER,
                            n_samples=N_SAMPLES)
            half = K0.shape[0] // 2
            qe_tot = np.array([sim.kernel(w, cra_deg=cra, f_number=F_NUMBER,
                                          n_samples=N_SAMPLES).sum() for w in WL])
            ax.plot(WL, qe_tot * T["G"] * 100, "k--", lw=1.2,
                    label="no spatial crosstalk")

            curves = {}
            for (pr, pc) in gpos:
                s = response(sim, WL, cra, pr, pc, T)
                curves[(pr, pc)] = s
                nb = neighbours(pr, pc, half)
                nk = sum(1 for o in ((-1, 0), (1, 0), (0, -1), (0, 1))
                         if nb[o] == "K")
                ax.plot(WL, s * 100, lw=1.3,
                        label="G(%d,%d)  %d K-neighbour%s"
                              % (pr, pc, nk, "" if nk == 1 else "s"))
                i550 = int(np.argmin(np.abs(WL - 550)))
                i940 = int(np.argmin(np.abs(WL - 940)))
                rows.append(dict(geometry=gname, cra=cra, r=pr, c=pc, n_k=nk,
                                 qe550=s[i550], qe940=s[i940],
                                 ref550=qe_tot[i550] * T["G"][i550]))
            arr = np.array(list(curves.values()))
            i550 = int(np.argmin(np.abs(WL - 550)))
            spread = (arr[:, i550].max() - arr[:, i550].min()) / arr[:, i550].mean()
            ax.set_title("%s   CRA %.0f deg   (spread at 550 nm = %.1f %%)"
                         % (gname, cra, spread * 100), fontsize=9)
            ax.set_ylabel("green-pixel QE [%]")
            ax.set_yscale("log")
            ax.set_ylim(1e-3, 100)
            ax.legend(fontsize=6.5, ncol=2)
            if row == 1:
                ax.set_xlabel("wavelength [nm]")
            print("  %-12s CRA %2.0f: spread %.2f %%   [%.0f s]"
                  % (gname, cra, spread * 100, time.time() - t0))

    fig.suptitle("Six green pixels of the RGB-IR 4x4 pattern under f/%.1f "
                 "illumination -- on-chip IR cut over R/G/B only, so their NIR "
                 "comes purely from K-cell crosstalk" % F_NUMBER, y=0.995)
    fig.tight_layout()
    fig.savefig(OUT / "fig14_rgbk_G_v2.png")
    plt.close(fig)

    hdr = list(rows[0].keys())
    with open(OUT / "rgbk_G_v2.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.5f" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    print("\n%-12s%6s%10s%8s%12s%12s%10s"
          % ("geometry", "CRA", "G(r,c)", "K-nbr", "QE550[%]", "QE940[%]",
             "vs ref"))
    for r in rows:
        print("%-12s%5.0f%10s%8d%11.2f%%%11.2f%%%9.1f%%"
              % (r["geometry"], r["cra"], "(%d,%d)" % (r["r"], r["c"]), r["n_k"],
                 r["qe550"] * 100, r["qe940"] * 100,
                 (r["qe550"] / r["ref550"] - 1) * 100))
    print("\n%.0f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
