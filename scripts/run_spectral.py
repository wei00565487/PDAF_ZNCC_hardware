"""Main demo: spectral crosstalk of a Bayer pixel for several DTI options.

Outputs (in out/):
  fig1_generation.png   photo-carrier generation cross-sections
  fig2_kernels.png      crosstalk kernels (share of signal per neighbour PD)
  fig3_spectral.png     QE / crosstalk vs wavelength, optical vs electrical
  fig4_response.png     Bayer channel spectral responses with & without crosstalk
  crosstalk_summary.csv, mixing_matrix.txt
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import (PixelStack, Simulator, optics, materials as M,
                   color_mixing_matrix, ccm_noise_gain)
from bxsim.plotting import kernel_heatmap, section_xz, BAYER_COLORS

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
WL = np.arange(400, 1001, 20.0)
PROBE = (450.0, 550.0, 650.0, 850.0)

BASE = dict(pitch_um=0.80, n_pix=5, si_thickness_um=3.0, pd_depth_um=1.0,
            pd_fill=0.75, ml_sag_um=0.35)
CONFIGS = {
    "no DTI":      dict(dti_enabled=False),
    "BDTI 1.5 um": dict(dti_enabled=True, dti_depth_um=1.5),
    "BDTI 2.6 um": dict(dti_enabled=True, dti_depth_um=2.6),
    "FDTI 3.0 um": dict(dti_enabled=True, dti_depth_um=3.0),
}


def main():
    t0 = time.time()
    sims, stacks = {}, {}
    for name, kw in CONFIGS.items():
        st = PixelStack(**BASE, **kw)
        stacks[name] = st
        sims[name] = Simulator(st, verbose=False)

    # ---------------- fig 1: generation profiles ------------------------
    ref = stacks["BDTI 2.6 um"]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.1))
    for k, (ax, w) in enumerate(zip(axes, PROBE)):
        G = optics.generation(ref, w, aperture="center")
        im = section_xz(ax, G, ref,
                        "%.0f nm  (1/alpha = %.2f um)" % (w, M.si_absorption_depth_um(w)),
                        ylabel=(k == 0))
    fig.colorbar(im, ax=axes, shrink=0.85, label="log10 normalised generation")
    fig.suptitle("Photo-carrier generation from light entering ONE CFA cell "
                 "(cyan = pixel borders, green dash = DTI bottom, "
                 "white dot = depletion edge)", y=1.06, fontsize=9)
    fig.savefig(OUT / "fig1_generation.png")
    plt.close(fig)
    print("[1/4] generation profiles                %5.1f s" % (time.time() - t0))

    # ---------------- fig 2: kernels ------------------------------------
    fig, axes = plt.subplots(len(CONFIGS), len(PROBE),
                             figsize=(2.5 * len(PROBE), 2.5 * len(CONFIGS)))
    for r, name in enumerate(CONFIGS):
        for c, w in enumerate(PROBE):
            K = sims[name].kernel(w)
            kernel_heatmap(axes[r, c], K,
                           "%s\n%.0f nm  own=%.1f%%" % (name, w, K[2, 2] / K.sum() * 100))
    fig.suptitle("Crosstalk kernel: % of the signal from one CFA cell "
                 "collected by each neighbouring photodiode", y=1.005, fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_kernels.png")
    plt.close(fig)
    print("[2/4] crosstalk kernels                  %5.1f s" % (time.time() - t0))

    # ---------------- fig 3: spectral sweep -----------------------------
    data = {}
    for name in CONFIGS:
        Ks = sims[name].kernel_spectrum(WL)
        Ki = sims[name].kernel_spectrum(WL, transport="ideal")
        tot = Ks.reshape(len(WL), -1).sum(1)
        toti = Ki.reshape(len(WL), -1).sum(1)
        data[name] = dict(K=Ks, qe=tot, own=Ks[:, 2, 2],
                          xt=(tot - Ks[:, 2, 2]) / tot,
                          xt_opt=(toti - Ki[:, 2, 2]) / toti)

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for name, d in data.items():
        axes[0].plot(WL, d["qe"] * 100, label=name)
        axes[1].plot(WL, d["xt"] * 100, label=name)
        axes[2].plot(WL, d["xt_opt"] * 100, ls="--", label=name + " optical")
        axes[2].plot(WL, (d["xt"] - d["xt_opt"]) * 100, ls="-",
                     label=name + " electrical")
    axes[0].set_ylabel("total QE of one CFA cell [%]")
    axes[1].set_ylabel("total crosstalk [%]")
    axes[2].set_ylabel("crosstalk contribution [%]")
    for a in axes:
        a.set_xlabel("wavelength [nm]")
        a.legend(fontsize=6.0)
    axes[0].set_title("collected / incident photons (clear filter)")
    axes[1].set_title("signal landing outside its own pixel")
    axes[2].set_title("optical (diffraction) vs electrical (diffusion)")
    fig.tight_layout()
    fig.savefig(OUT / "fig3_spectral.png")
    plt.close(fig)
    print("[3/4] spectral sweep                     %5.1f s" % (time.time() - t0))

    # ---------------- fig 4: channel responses + colour mixing ----------
    fig, axes = plt.subplots(1, len(CONFIGS), figsize=(3.4 * len(CONFIGS), 3.2),
                             sharey=True)
    summary, mixtxt = [], []
    for ax, (name, sim) in zip(np.atleast_1d(axes), sims.items()):
        res = sim.spectral_response(WL, ircf=True)
        for ch in ("R", "Gr", "B"):
            ax.plot(WL, res["resp"][ch] * 100, color=BAYER_COLORS[ch], label=ch)
            ax.plot(WL, res["resp_no_xtalk"][ch] * 100, color=BAYER_COLORS[ch],
                    ls=":", lw=1)
        ax.set_title(name)
        ax.set_xlabel("wavelength [nm]")
        Mx = color_mixing_matrix(res)
        C, gain = ccm_noise_gain(Mx)
        Mn = Mx / Mx.sum(1)[:, None]
        mixtxt.append(
            "### %s\n"
            "raw mixing matrix (rows = R,G,B channel; cols = colour the light\n"
            "actually passed through), row-normalised so white -> (1,1,1)\n" % name
            + "\n".join("  " + "  ".join("%7.4f" % v for v in row) for row in Mn)
            + "\n colour-correction matrix (its inverse):\n"
            + "\n".join("  " + "  ".join("%7.3f" % v for v in row) for row in C)
            + "\n CCM noise gain  R=%.2f  G=%.2f  B=%.2f\n" % tuple(gain))
        purity = np.diag(Mn)
        summary.append(dict(
            config=name,
            qe550=float(np.interp(550, WL, data[name]["qe"])),
            xt450=float(np.interp(450, WL, data[name]["xt"])),
            xt550=float(np.interp(550, WL, data[name]["xt"])),
            xt650=float(np.interp(650, WL, data[name]["xt"])),
            xt850=float(np.interp(850, WL, data[name]["xt"])),
            purity_R=purity[0], purity_G=purity[1], purity_B=purity[2],
            ccm_gain_R=gain[0], ccm_gain_G=gain[1], ccm_gain_B=gain[2]))
    np.atleast_1d(axes)[0].set_ylabel("channel QE [%]  (dotted = crosstalk removed)")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    fig.suptitle("Bayer channel spectral response with IR-cut filter", y=1.02)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_response.png")
    plt.close(fig)

    hdr = list(summary[0].keys())
    with open(OUT / "crosstalk_summary.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for row in summary:
            f.write(",".join("%.4f" % row[k] if isinstance(row[k], float) else str(row[k])
                             for k in hdr) + "\n")
    (OUT / "mixing_matrix.txt").write_text("\n\n".join(mixtxt), encoding="utf-8")

    print("[4/4] channel responses / colour matrix  %5.1f s\n" % (time.time() - t0))
    print("%-13s%7s%8s%8s%8s%8s%8s%8s%8s%8s%8s"
          % ("config", "QE550", "XT450", "XT550", "XT650", "XT850",
             "purR", "purG", "purB", "gainR", "gainB"))
    for r in summary:
        print("%-13s%6.1f%%%7.1f%%%7.1f%%%7.1f%%%7.1f%%%8.3f%8.3f%8.3f%8.2f%8.2f"
              % (r["config"], r["qe550"] * 100, r["xt450"] * 100, r["xt550"] * 100,
                 r["xt650"] * 100, r["xt850"] * 100, r["purity_R"], r["purity_G"],
                 r["purity_B"], r["ccm_gain_R"], r["ccm_gain_B"]))
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
