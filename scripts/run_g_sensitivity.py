"""Green-pixel sensitivity spread with NO active IR source, 3.0 um pixel.

Six green pixels of the RGB-IR 4x4 cell, under
  * a 6500 K blackbody (integrated 400-1000 nm, and 400-700 nm for comparison),
  * monochromatic 450 / 550 / 650 nm.

Even with no IR emitter, a blackbody still radiates in the NIR, and the K cells
have no IR cut -- so that NIR reaches the K photodiodes and crosstalks into the
neighbouring greens.  Reporting the 400-700 nm integral separately shows how
much of the spread is that ambient-NIR path and how much is purely visible.

Stack: 3.0 um pitch, 6.0 um Si, full-depth DTI, 3.0 um depletion, 100 %
aperture, 0.30 um on-chip IR cut over R/G/B, low-index CFA grid, f/1.8.

Outputs: out/fig15_g_sensitivity.png, out/g_sensitivity.csv
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import PixelStack, Simulator, planck

sys.path.insert(0, str(ROOT / "scripts"))
from run_rgbk import transmittance, g_positions, neighbours, PATTERN  # noqa: E402

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

F_NUM, NS = 1.8, 16
CRAS = (0.0, 30.0)
WL = np.arange(400, 1001, 20.0)
MONO = (450.0, 550.0, 650.0)

STACK = dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
             pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0, dti_width_um=0.20,
             ml_sag_um=0.80, t_ml_to_cfa_um=0.10, t_cfa_um=0.90,
             t_cfa_to_si_um=0.20, t_ircf_um=0.30, cfa_grid_enabled=True,
             cfa_grid_width_um=0.15, dx_opt_nm=50.0, dz_opt_nm=50.0,
             dx_diff_nm=100.0, dz_diff_nm=100.0)


def responses(sim, wl, cra, T):
    """(6, len(wl)) array of green-pixel QE."""
    gp = g_positions()
    out = np.zeros((len(gp), len(wl)))
    for k, w in enumerate(wl):
        K = sim.kernel(w, cra_deg=cra, f_number=F_NUM, n_samples=NS)
        half = K.shape[0] // 2
        for g, (pr, pc) in enumerate(gp):
            nb = neighbours(pr, pc, half)
            out[g, k] = sum(T[nb[(i, j)]][k] * K[i + half, j + half]
                            for i in range(-half, half + 1)
                            for j in range(-half, half + 1))
    return out


def main():
    t0 = time.time()
    gp = g_positions()
    sim = Simulator(PixelStack(**STACK), verbose=False)

    T_full = {c: transmittance(c, WL) for c in "RGBK"}
    T_mono = {c: transmittance(c, np.array(MONO)) for c in "RGBK"}

    rows, store = [], {}
    for cra in CRAS:
        S = responses(sim, WL, cra, T_full)
        Sm = responses(sim, np.array(MONO), cra, T_mono)
        print("  CRA %2.0f done  %5.0f s" % (cra, time.time() - t0))

        phi = planck(WL, 6500.0)
        dwl = np.gradient(WL)
        vis = WL <= 700
        cases = {
            "6500 K (400-1000 nm)": (S * phi * dwl).sum(axis=1),
            "6500 K (400-700 nm)": (S[:, vis] * phi[vis] * dwl[vis]).sum(axis=1),
        }
        for k, w in enumerate(MONO):
            cases["%.0f nm mono" % w] = Sm[:, k]

        store[cra] = cases
        for cname, v in cases.items():
            rel = v / v.mean()
            for g, (pr, pc) in enumerate(gp):
                rows.append(dict(cra=cra, illuminant=cname, r=pr, c=pc,
                                 signal=v[g], rel=rel[g]))

    # ---------------- figure ------------------------------------------
    names = list(store[CRAS[0]].keys())
    fig, axes = plt.subplots(1, len(CRAS), figsize=(7.2 * len(CRAS), 4.4),
                             sharey=True)
    xs = np.arange(len(gp))
    for ax, cra in zip(np.atleast_1d(axes), CRAS):
        w = 0.8 / len(names)
        for i, cname in enumerate(names):
            v = store[cra][cname]
            ax.bar(xs + (i - (len(names) - 1) / 2) * w, (v / v.mean() - 1) * 100,
                   width=w * 0.92, label=cname)
        ax.set_xticks(xs, ["G(%d,%d)" % p for p in gp], fontsize=8)
        ax.axhline(0, color="#333", lw=0.8)
        ax.set_ylabel("deviation from the six-pixel mean [%]")
        ax.set_title("3.0 um pixel, CRA %.0f deg, f/1.8, no active IR" % cra)
        ax.legend(fontsize=7.5)
    fig.suptitle("Green-pixel sensitivity spread in the RGB-IR 4x4 cell", y=0.99)
    fig.tight_layout()
    fig.savefig(OUT / "fig15_g_sensitivity.png")
    plt.close(fig)

    hdr = list(rows[0].keys())
    with open(OUT / "g_sensitivity.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.6g" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    for cra in CRAS:
        print("\n=== CRA %.0f deg ===" % cra)
        print("%-22s" % "illuminant"
              + "".join("%10s" % ("G%d,%d" % p) for p in gp) + "%10s" % "max-min")
        for cname in names:
            v = store[cra][cname]
            rel = (v / v.mean() - 1) * 100
            print("%-22s" % cname + "".join("%9.2f%%" % r for r in rel)
                  + "%9.2f%%" % (v.max() / v.min() * 100 - 100))
    print("\n%.0f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
