"""What the f-number of the taking lens does to QE and crosstalk.

A sensor never sees a plane wave.  An f/N lens delivers a cone of half-angle
asin(1/2N) around the chief ray, and every ray in that cone walks a different
distance sideways through the CFA-to-silicon gap.  For a flat field the exit
pupil is an incoherent source, so the plane-wave components add in intensity;
`optics.generation_cone` does exactly that with a uniform-weight quadrature
over the direction-cosine disk.

Outputs: out/fig11_fnumber.png, out/fnumber.csv
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import PixelStack, Simulator

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

WL = np.arange(400, 1001, 20.0)
CRAS = (0.0, 10.0, 20.0, 30.0)
FNUMS = (1.4, 1.8, 2.8, 5.6)
NS = 16

GEOMS = {
    "3.0um FDTI": dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
                       pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0,
                       dti_width_um=0.20, ml_sag_um=0.80, t_ml_to_cfa_um=0.10,
                       t_cfa_um=0.90, t_cfa_to_si_um=0.20, dx_opt_nm=50.0,
                       dz_opt_nm=50.0, dx_diff_nm=100.0, dz_diff_nm=100.0),
    "0.8um FDTI": dict(pitch_um=0.80, n_pix=3, si_thickness_um=3.0, pd_depth_um=1.0,
                       pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True,
                       dti_depth_um=3.0),
}


def main():
    t0 = time.time()
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 7.4))

    for col, (gname, kw) in enumerate(GEOMS.items()):
        sim = Simulator(PixelStack(**kw), verbose=False)
        h = kw["n_pix"] // 2

        # ---- panel: crosstalk at 550 nm vs CRA, per f-number ----------
        ax = axes[0, col]
        for f in (None,) + FNUMS:
            xt, qe = [], []
            for cra in CRAS:
                K = sim.kernel(550.0, cra_deg=cra, f_number=f, n_samples=NS)
                xt.append((1 - K[h, h] / K.sum()) * 100)
                qe.append(K.sum() * 100)
                rows.append(dict(geometry=gname, f_number=(f or 0.0), cra=cra,
                                 qe550=qe[-1], xt550=xt[-1]))
            lab = "plane wave" if f is None else "f/%.1f" % f
            ax.plot(CRAS, xt, "-o", ms=3.5, lw=1.4,
                    ls="--" if f is None else "-", label=lab)
        ax.set_xlabel("chief ray angle [deg]")
        ax.set_ylabel("crosstalk at 550 nm [%]")
        ax.set_title("%s -- crosstalk vs f-number" % gname)
        ax.legend(fontsize=7)
        print("  %-12s crosstalk panel   %5.0f s" % (gname, time.time() - t0))

        # ---- panel: spectra, plane wave vs f/1.8, CRA 0 and 30 --------
        ax = axes[1, col]
        for cra, c in ((0.0, "#1f77b4"), (30.0, "#d62728")):
            for f, ls in ((None, "--"), (1.8, "-")):
                v = [(1 - K[h, h] / K.sum()) * 100 for K in
                     (sim.kernel(w, cra_deg=cra, f_number=f, n_samples=NS)
                      for w in WL)]
                ax.plot(WL, v, ls, color=c, lw=1.4,
                        label="CRA %.0f, %s" % (cra, "plane wave" if f is None
                                                else "f/1.8"))
        ax.set_xlabel("wavelength [nm]")
        ax.set_ylabel("crosstalk [%]")
        ax.set_title("%s -- spectra" % gname)
        ax.legend(fontsize=7)
        print("  %-12s spectra panel     %5.0f s" % (gname, time.time() - t0))

    fig.suptitle("Illumination from an f/N lens (cone half-angle asin(1/2N)) "
                 "versus a collimated plane wave", y=0.995)
    fig.tight_layout()
    fig.savefig(OUT / "fig11_fnumber.png")
    plt.close(fig)

    hdr = list(rows[0].keys())
    with open(OUT / "fnumber.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.4f" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    print("\n%-12s%12s%8s%11s%11s" % ("geometry", "illum", "CRA", "QE550[%]",
                                      "XT550[%]"))
    for r in rows:
        lab = "plane wave" if r["f_number"] == 0.0 else "f/%.1f" % r["f_number"]
        print("%-12s%12s%8.0f%11.2f%11.3f"
              % (r["geometry"], lab, r["cra"], r["qe550"], r["xt550"]))
    print("\n%.0f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
