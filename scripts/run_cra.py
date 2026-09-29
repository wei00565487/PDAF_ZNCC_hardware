"""Chief-ray-angle sweep: crosstalk and shading away from the optical axis.

At the edge of the array the chief ray arrives tilted, so the microlens spot
walks off its own photodiode.  This is the dominant cause of colour shading in
small-pitch sensors.  The script also shows what a microlens shift (the usual
countermeasure) recovers.

Outputs: out/fig5_cra.png, out/cra_sweep.csv
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

ANGLES = np.arange(0.0, 31.0, 5.0)
WLS = (450.0, 550.0, 650.0)
BASE = dict(pitch_um=0.80, n_pix=5, si_thickness_um=3.0, pd_depth_um=1.0,
            pd_fill=0.75, ml_sag_um=0.35, dti_enabled=True, dti_depth_um=2.6)


def sweep(ml_shift_um):
    """Return dict wl -> (own, xtalk, asymmetry) arrays over ANGLES."""
    # the carrier-transport solve does not depend on the illumination, so one
    # Simulator (one adjoint solve) covers the whole sweep
    st = PixelStack(**BASE, ml_shift_um=ml_shift_um, ml_shift_az_deg=0.0)
    sim = Simulator(st, verbose=False)
    res = {}
    for wl in WLS:
        own, xt, asym = [], [], []
        for a in ANGLES:
            K = sim.kernel(wl, cra_deg=a, azimuth_deg=0.0)
            tot = K.sum()
            own.append(K[2, 2] / tot)
            xt.append(1 - K[2, 2] / tot)
            # signal pulled towards +x versus -x (columns are x)
            asym.append((K[:, 3:].sum() - K[:, :2].sum()) / tot)
        res[wl] = (np.array(own), np.array(xt), np.array(asym))
    return res


def main():
    t0 = time.time()
    # A ray tilted towards +x lands at +x on the silicon, so the microlens has
    # to be moved the other way for its spot to fall back onto its own diode.
    # walk = stack height * tan(refracted angle)
    st0 = PixelStack(**BASE)
    n = st0.n_planar
    shift = -st0.stack_height_um * np.tan(np.arcsin(np.sin(np.deg2rad(20.0)) / n))
    print("microlens shift chosen for 20 deg CRA: %+.3f um" % shift)

    r0 = sweep(0.0)
    print("  no-shift sweep done   %5.1f s" % (time.time() - t0))
    r1 = sweep(shift)
    print("  shifted sweep done    %5.1f s" % (time.time() - t0))

    fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
    for wl in WLS:
        c = {450.0: "#1f77b4", 550.0: "#2ca02c", 650.0: "#d62728"}[wl]
        axes[0].plot(ANGLES, r0[wl][0] * 100, "-o", ms=3, color=c,
                     label="%.0f nm, no shift" % wl)
        axes[0].plot(ANGLES, r1[wl][0] * 100, "--s", ms=3, color=c,
                     label="%.0f nm, ML shift %+.2f um" % (wl, shift))
        axes[1].plot(ANGLES, r0[wl][1] * 100, "-o", ms=3, color=c)
        axes[1].plot(ANGLES, r1[wl][1] * 100, "--s", ms=3, color=c)
        axes[2].plot(ANGLES, r0[wl][2] * 100, "-o", ms=3, color=c)
        axes[2].plot(ANGLES, r1[wl][2] * 100, "--s", ms=3, color=c)
    axes[0].set_ylabel("own-pixel share of the signal [%]")
    axes[1].set_ylabel("crosstalk [%]")
    axes[2].set_ylabel("+x minus -x share [%]  (directional leak)")
    for a in axes:
        a.set_xlabel("chief ray angle [deg]")
    axes[0].legend(fontsize=6.5)
    axes[0].set_title("solid = no microlens shift, dashed = shifted")
    axes[1].set_title("total crosstalk vs field position")
    axes[2].set_title("asymmetry -> colour shading")
    fig.tight_layout()
    fig.savefig(OUT / "fig5_cra.png")
    plt.close(fig)

    with open(OUT / "cra_sweep.csv", "w", encoding="utf-8") as f:
        f.write("wavelength_nm,cra_deg,ml_shift_um,own_share,crosstalk,asymmetry\n")
        for tag, r, sh in (("noshift", r0, 0.0), ("shift", r1, shift)):
            for wl in WLS:
                own, xt, asym = r[wl]
                for i, a in enumerate(ANGLES):
                    f.write("%.0f,%.1f,%.3f,%.5f,%.5f,%.5f\n"
                            % (wl, a, sh, own[i], xt[i], asym[i]))

    print("\n%-9s%-9s%12s%12s%12s" % ("wl[nm]", "CRA[deg]", "own_noshift",
                                      "own_shift", "asym_noshift"))
    for wl in WLS:
        for i, a in enumerate(ANGLES):
            if a % 10:
                continue
            print("%-9.0f%-9.0f%11.1f%%%11.1f%%%11.1f%%"
                  % (wl, a, r0[wl][0][i] * 100, r1[wl][0][i] * 100,
                     r0[wl][2][i] * 100))
    print("\nwrote %s" % OUT)


if __name__ == "__main__":
    main()
