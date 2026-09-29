"""Adding a 0.30 um on-chip IR-cut filter and a low-index grid between the
colour filter cells, under f/1.8 illumination, with the NIR band at 940 nm.

The two changes pull in opposite directions:

  * the IR-cut filter is 0.30 um of extra material between the microlens and
    the silicon, so it pushes the stack height up and makes crosstalk worse;
  * the low-index grid turns each colour filter cell into a short waveguide,
    which confines the light and makes crosstalk better.

The grid is modelled as a real lateral index step handled by a split-step BPM
(guiding is what BPM is for), not as an absorbing wall like the DTI.

Outputs: out/fig13_grid_ircf.png, out/grid_ircf.csv
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

F_NUM, NS = 1.8, 16
PROBE = (450.0, 550.0, 650.0, 940.0)
WL = np.arange(400, 1001, 25.0)
CRAS = (0.0, 30.0)

BASE3 = dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
             pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0, dti_width_um=0.20,
             ml_sag_um=0.80, t_ml_to_cfa_um=0.10, t_cfa_um=0.90,
             t_cfa_to_si_um=0.20, dx_opt_nm=50.0, dz_opt_nm=50.0,
             dx_diff_nm=100.0, dz_diff_nm=100.0)
BASE08 = dict(pitch_um=0.80, n_pix=3, si_thickness_um=3.0, pd_depth_um=1.0,
              pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True, dti_depth_um=3.0)

VARIANTS = {
    "3.0um": [
        ("baseline", dict(BASE3)),
        ("+0.30um IRCF", dict(BASE3, t_ircf_um=0.30)),
        ("+IRCF +LI grid", dict(BASE3, t_ircf_um=0.30, cfa_grid_enabled=True,
                                cfa_grid_width_um=0.15)),
    ],
    "0.8um": [
        ("baseline", dict(BASE08)),
        ("+0.30um IRCF", dict(BASE08, t_ircf_um=0.30)),
        ("+IRCF +LI grid", dict(BASE08, t_ircf_um=0.30, cfa_grid_enabled=True,
                                cfa_grid_width_um=0.10)),
    ],
}


def main():
    t0 = time.time()
    rows = []
    fig, axes = plt.subplots(2, 2, figsize=(12.5, 7.6))

    for col, (gname, variants) in enumerate(VARIANTS.items()):
        sims = {}
        for vname, kw in variants:
            st = PixelStack(**kw)
            sims[vname] = (Simulator(st, verbose=False), st)

        # ---- table over the probe wavelengths -------------------------
        for vname, (sim, st) in sims.items():
            h = st.n_pix // 2
            for cra in CRAS:
                for w in PROBE:
                    K = sim.kernel(w, cra_deg=cra, f_number=F_NUM, n_samples=NS)
                    rows.append(dict(geometry=gname, variant=vname,
                                     stack_h=st.stack_height_um, cra=cra, wl=w,
                                     qe=K.sum() * 100,
                                     xt=(1 - K[h, h] / K.sum()) * 100))
            print("  %-6s %-16s table   %5.0f s" % (gname, vname, time.time() - t0))

        # ---- spectra --------------------------------------------------
        for r, cra in enumerate(CRAS):
            ax = axes[r, col]
            for vname, (sim, st) in sims.items():
                h = st.n_pix // 2
                v = [(1 - K[h, h] / K.sum()) * 100 for K in
                     (sim.kernel(w, cra_deg=cra, f_number=F_NUM, n_samples=NS)
                      for w in WL)]
                ax.plot(WL, v, lw=1.5,
                        label="%s (stack %.2f um)" % (vname, st.stack_height_um))
            ax.axvline(940, color="#888", lw=0.8, ls=":")
            ax.text(944, ax.get_ylim()[1] * 0.95, "940 nm", fontsize=7, color="#555")
            ax.set_xlabel("wavelength [nm]")
            ax.set_ylabel("crosstalk [%]")
            ax.set_title("%s pitch, CRA %.0f deg, f/%.1f" % (gname, cra, F_NUM))
            ax.legend(fontsize=7)
            print("  %-6s CRA %2.0f spectra          %5.0f s"
                  % (gname, cra, time.time() - t0))

    fig.suptitle("On-chip IR-cut thickness vs low-index CFA grid, f/1.8 "
                 "illumination", y=0.995)
    fig.tight_layout()
    fig.savefig(OUT / "fig13_grid_ircf.png")
    plt.close(fig)

    hdr = list(rows[0].keys())
    with open(OUT / "grid_ircf.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.4f" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    print("\n%-8s%-17s%9s%6s%8s%9s%9s"
          % ("pitch", "variant", "stack", "CRA", "wl", "QE[%]", "XT[%]"))
    for r in rows:
        print("%-8s%-17s%8.2f%6.0f%8.0f%9.2f%9.3f"
              % (r["geometry"], r["variant"], r["stack_h"], r["cra"], r["wl"],
                 r["qe"], r["xt"]))
    print("\n%.0f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
