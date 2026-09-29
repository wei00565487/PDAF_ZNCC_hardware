"""Large-pixel case: 3.0 um pitch, 6.0 um silicon, full-depth DTI,
3.0 um depletion depth, 100 % photodiode aperture.

Compared against the 0.8 um baseline from run_spectral.py.

The optical DTI model is the honest weak point here: bxsim's BPM treats the
trench as an ABSORBER, while a real oxide-filled trench REFLECTS light back
into its own pixel.  So the run is done twice to bracket the truth:

  'absorbing trench'  -> correct crosstalk, pessimistic QE
  'optically open'    -> correct QE, pessimistic crosstalk
                         (electrical isolation still full-depth)

Outputs: out/fig7_case3um.png, out/case3um.csv
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

# Geometry scaled to a 3 um pixel.  A spherical microlens cannot focus a 3 um
# cell onto a plane closer than ~5 um (a hemisphere of radius = the half
# diagonal already gives f = 5.2 um), so a large pixel is always underfocused.
# With a 100 % aperture and full-depth DTI that costs nothing.
CASE = dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0,
            pd_depth_um=3.0, pd_fill=1.00,
            dti_enabled=True, dti_depth_um=6.0, dti_width_um=0.20,
            ml_sag_um=0.80, t_ml_to_cfa_um=0.10, t_cfa_um=0.90,
            t_cfa_to_si_um=0.20,
            dx_opt_nm=50.0, dz_opt_nm=50.0, dx_diff_nm=100.0, dz_diff_nm=100.0)

BASE08 = dict(pitch_um=0.80, n_pix=5, si_thickness_um=3.0, pd_depth_um=1.0,
              pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True, dti_depth_um=3.0)

CONFIGS = {
    "3.0um FDTI (absorbing trench)": dict(CASE, dti_blocks_light=True),
    "3.0um FDTI (optically open)":   dict(CASE, dti_blocks_light=False),
    "0.8um FDTI (baseline)":         BASE08,
}


def main():
    t0 = time.time()
    st = PixelStack(**CONFIGS["3.0um FDTI (absorbing trench)"])
    print("microlens ROC = %.2f um, f = %.2f um, stack height = %.2f um"
          % (st.ml_roc_um, st.ml_focus_um, st.stack_height_um))
    print("trench area fraction = %.1f %%"
          % ((1 - ((st.pitch_um - st.dti_width_um) / st.pitch_um) ** 2) * 100))

    sims, data = {}, {}
    for name, kw in CONFIGS.items():
        sims[name] = Simulator(PixelStack(**kw), verbose=False)

    for name, sim in sims.items():
        Ks = sim.kernel_spectrum(WL)
        Ki = sim.kernel_spectrum(WL, transport="ideal")
        h = Ks.shape[-1] // 2
        tot = Ks.reshape(len(WL), -1).sum(1)
        toti = Ki.reshape(len(WL), -1).sum(1)
        data[name] = dict(K=Ks, qe=tot, own=Ks[:, h, h],
                          xt=(tot - Ks[:, h, h]) / tot,
                          xt_opt=(toti - Ki[:, h, h]) / toti)
        print("  %-32s %5.1f s" % (name, time.time() - t0))

    # ------------------------------------------------------------------
    fig = plt.figure(figsize=(13.5, 7.4))
    gs = fig.add_gridspec(2, 4, height_ratios=[1.0, 1.0])

    ref = sims["3.0um FDTI (absorbing trench)"].stack
    for k, w in enumerate(PROBE):
        ax = fig.add_subplot(gs[0, k])
        G = optics.generation(ref, w, aperture="center")
        im = section_xz(ax, G, ref, "%.0f nm" % w, ylabel=(k == 0))

    ax = fig.add_subplot(gs[1, 0])
    kernel_heatmap(ax, sims["3.0um FDTI (absorbing trench)"].kernel(550.0),
                   "kernel 550 nm\n3.0um, absorbing trench")
    ax = fig.add_subplot(gs[1, 1])
    kernel_heatmap(ax, sims["3.0um FDTI (optically open)"].kernel(550.0),
                   "kernel 550 nm\n3.0um, optically open")

    ax = fig.add_subplot(gs[1, 2])
    for name, d in data.items():
        ax.plot(WL, d["qe"] * 100, label=name)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("total QE [%]")
    ax.legend(fontsize=6)
    ax.set_title("quantum efficiency")

    ax = fig.add_subplot(gs[1, 3])
    for name, d in data.items():
        ax.semilogy(WL, np.maximum(d["xt"] * 100, 1e-4), label=name)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("total crosstalk [%]")
    ax.legend(fontsize=6)
    ax.set_title("crosstalk (log scale)")

    fig.suptitle("3.0 um pitch / 6.0 um Si / full-depth DTI / 3.0 um depletion "
                 "/ 100 % aperture", y=1.00)
    fig.tight_layout()
    fig.savefig(OUT / "fig7_case3um.png")
    plt.close(fig)

    # ------------------------------------------------------------------
    rows = []
    for name, sim in sims.items():
        res = sim.spectral_response(WL, ircf=True)
        Mx = color_mixing_matrix(res)
        C, gain = ccm_noise_gain(Mx)
        Mn = Mx / Mx.sum(1)[:, None]
        d = data[name]
        rows.append(dict(
            config=name,
            qe450=float(np.interp(450, WL, d["qe"])),
            qe550=float(np.interp(550, WL, d["qe"])),
            qe850=float(np.interp(850, WL, d["qe"])),
            xt450=float(np.interp(450, WL, d["xt"])),
            xt550=float(np.interp(550, WL, d["xt"])),
            xt650=float(np.interp(650, WL, d["xt"])),
            xt850=float(np.interp(850, WL, d["xt"])),
            xt_elec550=float(np.interp(550, WL, d["xt"] - d["xt_opt"])),
            purity_R=Mn[0, 0], purity_G=Mn[1, 1], purity_B=Mn[2, 2],
            gain_R=gain[0], gain_G=gain[1], gain_B=gain[2]))

    hdr = list(rows[0].keys())
    with open(OUT / "case3um.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.5f" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    print("\n%-32s%8s%8s%8s%9s%9s%9s%9s%10s" %
          ("config", "QE450", "QE550", "QE850", "XT450", "XT550",
           "XT650", "XT850", "XT_elec550"))
    for r in rows:
        print("%-32s%7.1f%%%7.1f%%%7.1f%%%8.3f%%%8.3f%%%8.3f%%%8.3f%%%9.4f%%" %
              (r["config"], r["qe450"] * 100, r["qe550"] * 100, r["qe850"] * 100,
               r["xt450"] * 100, r["xt550"] * 100, r["xt650"] * 100,
               r["xt850"] * 100, r["xt_elec550"] * 100))
    print("\n%-32s%9s%9s%9s%9s%9s" %
          ("config", "purR", "purG", "purB", "gainR", "gainB"))
    for r in rows:
        print("%-32s%9.3f%9.3f%9.3f%9.2f%9.2f" %
              (r["config"], r["purity_R"], r["purity_G"], r["purity_B"],
               r["gain_R"], r["gain_B"]))
    print("\n%.1f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
