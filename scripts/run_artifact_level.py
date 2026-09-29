"""Is the narrow-band Gr/Gb (and 6-green) mismatch actually visible?

A large *relative* mismatch on a small signal may still be harmless.  This
script converts it into electrons at a realistic exposure and compares it with
the shot noise, and then pushes it through white balance + colour correction to
see what reaches the output image.

Scenes (all at an exposure that puts the RED channel at 50 % of full well):
  * 650 nm monochromatic          -- laser / narrow LED, worst case
  * 630 nm LED, 20 nm FWHM        -- tail lamp, traffic light
  * broadband red object under 6500 K
  * neutral grey under 6500 K     -- reference

Outputs: out/fig16_artifact_level.png, out/artifact_level.csv
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import PixelStack, Simulator, planck
import run_rgbk as R                                                # noqa: E402

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

WL = np.arange(400, 1001, 10.0)
F_NUM, NS = 1.8, 16
FULL_WELL_E = 20000.0
RED_LEVEL = 0.50            # red channel at 50 % of full well
READ_E = 3.0

STACK = dict(pitch_um=3.0, n_pix=3, si_thickness_um=6.0, pd_depth_um=3.0,
             pd_fill=1.00, dti_enabled=True, dti_depth_um=6.0, dti_width_um=0.20,
             ml_sag_um=0.80, t_ml_to_cfa_um=0.10, t_cfa_um=0.90,
             t_cfa_to_si_um=0.20, t_ircf_um=0.30, cfa_grid_enabled=True,
             cfa_grid_width_um=0.15, dx_opt_nm=50.0, dz_opt_nm=50.0,
             dx_diff_nm=100.0, dz_diff_nm=100.0)

BAYER = ["RG", "GB"]
BPOS = {"R": (0, 0), "Gr": (0, 1), "Gb": (1, 0), "B": (1, 1)}


def scenes():
    d65 = planck(WL, 6500.0)
    d65 = d65 / d65.max()
    gauss = np.exp(-0.5 * ((WL - 630.0) / (20.0 / 2.355)) ** 2)
    mono = (np.abs(WL - 650.0) < 5.0).astype(float)
    red_refl = 1.0 / (1.0 + np.exp(-(WL - 610.0) / 15.0))     # long-pass object
    return {
        "650 nm mono": mono,
        "630 nm LED (20 nm)": gauss,
        "red object / 6500 K": d65 * red_refl,
        "neutral grey / 6500 K": d65 * 0.18,
    }


def channel_signals(sim, cra, T, pattern, positions):
    """QE spectra of the named positions in `pattern`."""
    npx = len(pattern)
    out = {}
    Ks = [sim.kernel(w, cra_deg=cra, f_number=F_NUM, n_samples=NS) for w in WL]
    h = Ks[0].shape[0] // 2
    for name, (pr, pc) in positions.items():
        s = np.zeros(len(WL))
        for k, K in enumerate(Ks):
            s[k] = sum(T[pattern[(pr - i) % npx][(pc - j) % npx]][k]
                       * K[i + h, j + h]
                       for i in range(-h, h + 1) for j in range(-h, h + 1))
        out[name] = s
    return out


def main():
    t0 = time.time()
    sim = Simulator(PixelStack(**STACK), verbose=False)
    T = {c: R.transmittance(c, WL) for c in "RGBK"}
    dwl = np.gradient(WL)
    sc = scenes()

    rows = []
    for cra in (0.0, 30.0):
        qe = channel_signals(sim, cra, T, BAYER, BPOS)
        print("  CRA %2.0f spectra   %5.0f s" % (cra, time.time() - t0))

        # white-balance gains: what makes a 6500 K white read (1, 1, 1)
        d65 = planck(WL, 6500.0)
        base = np.array([np.sum(d65 * qe[c] * dwl) for c in ("R", "Gr", "B")])

        for sname, spec in sc.items():
            sig = {c: np.sum(spec * qe[c] * dwl) for c in ("R", "Gr", "Gb", "B")}
            scale = (RED_LEVEL * FULL_WELL_E) / max(sig["R"], 1e-30)
            e = {c: sig[c] * scale for c in sig}
            g_mean = 0.5 * (e["Gr"] + e["Gb"])
            d_e = e["Gr"] - e["Gb"]
            sigma = np.sqrt(max(g_mean, 0.0) + READ_E ** 2)
            rows.append(dict(cra=cra, scene=sname, R_e=e["R"], G_e=g_mean,
                             B_e=e["B"], dG_e=d_e,
                             dG_rel=d_e / max(g_mean, 1e-30) * 100,
                             sigma_e=sigma, snr_artifact=abs(d_e) / sigma,
                             wb_gain_G=base[0] / base[1]))

    hdr = list(rows[0].keys())
    with open(OUT / "artifact_level.csv", "w", encoding="utf-8") as f:
        f.write(",".join(hdr) + "\n")
        for r in rows:
            f.write(",".join("%.6g" % r[k] if isinstance(r[k], float) else str(r[k])
                             for k in hdr) + "\n")

    print("\n%-6s%-22s%10s%10s%10s%9s%9s%9s"
          % ("CRA", "scene", "R[e-]", "G[e-]", "dG[e-]", "dG[%]", "shot",
             "dG/sigma"))
    for r in rows:
        print("%-6.0f%-22s%10.0f%10.0f%10.1f%8.2f%%%9.1f%9.2f"
              % (r["cra"], r["scene"], r["R_e"], r["G_e"], r["dG_e"],
                 r["dG_rel"], r["sigma_e"], r["snr_artifact"]))

    # ---------------- figure ------------------------------------------
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
    names = list(sc.keys())
    for ax, cra in zip(axes, (0.0, 30.0)):
        sel = [r for r in rows if r["cra"] == cra]
        x = np.arange(len(sel))
        ax.bar(x - 0.2, [r["dG_rel"] for r in sel], 0.38,
               label="Gr-Gb mismatch [%]")
        ax.bar(x + 0.2, [r["snr_artifact"] for r in sel], 0.38,
               label="artifact / shot noise")
        ax.axhline(1.0, color="#c00", lw=1.0, ls="--")
        ax.text(len(sel) - 0.5, 1.15, "artifact = 1 sigma", fontsize=7,
                color="#c00", ha="right")
        ax.set_xticks(x, [n.replace(" / ", "\n") for n in names], fontsize=7.5)
        ax.set_yscale("symlog", linthresh=1.0)
        ax.set_title("3.0 um Bayer, CRA %.0f deg, f/1.8, red at 50 %% full well"
                     % cra)
        ax.legend(fontsize=7.5)
    fig.suptitle("Relative mismatch vs what actually reaches the image", y=0.99)
    fig.tight_layout()
    fig.savefig(OUT / "fig16_artifact_level.png")
    plt.close(fig)
    print("\n%.0f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
