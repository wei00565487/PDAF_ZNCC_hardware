"""What the crosstalk actually costs you in the ISP.

Crosstalk desaturates the raw colours, so the colour-correction matrix has to
be stronger, and a stronger CCM amplifies noise.  This script takes the 3x3
mixing matrix produced by the physical simulation, runs a synthetic colour
chart through it, adds shot + read noise at a realistic signal level, applies
the matching CCM and measures the colour noise that comes back out.

Outputs: out/fig6_image.png, out/ccm_noise.csv
"""
import sys
import time
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import matplotlib.pyplot as plt

from bxsim import PixelStack, Simulator, color_mixing_matrix, ccm_noise_gain

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
rng = np.random.default_rng(7)

WL = np.arange(400, 741, 20.0)
BASE = dict(pitch_um=0.80, n_pix=5, si_thickness_um=3.0, pd_depth_um=1.0,
            pd_fill=0.75, ml_sag_um=0.35)
CONFIGS = {
    "ideal (no crosstalk)": None,
    "no DTI":               dict(dti_enabled=False),
    "BDTI 1.5 um":          dict(dti_enabled=True, dti_depth_um=1.5),
    "FDTI 3.0 um":          dict(dti_enabled=True, dti_depth_um=3.0),
}

SIGNAL_E = 2000.0     # electrons in a mid-grey patch
READ_E = 2.0
PATCH = 56

# a 6x4 chart of linear-RGB patches (sRGB primaries/secondaries, skin, greys)
CHART = np.array([
    [0.35, 0.19, 0.14], [0.62, 0.40, 0.32], [0.16, 0.22, 0.38],
    [0.14, 0.20, 0.10], [0.28, 0.26, 0.46], [0.20, 0.58, 0.48],
    [0.75, 0.30, 0.06], [0.10, 0.13, 0.42], [0.60, 0.16, 0.20],
    [0.13, 0.07, 0.19], [0.44, 0.60, 0.10], [0.80, 0.45, 0.05],
    [0.05, 0.07, 0.32], [0.11, 0.38, 0.12], [0.45, 0.06, 0.08],
    [0.88, 0.72, 0.03], [0.55, 0.15, 0.35], [0.02, 0.35, 0.45],
    [0.95, 0.95, 0.95], [0.62, 0.62, 0.62], [0.38, 0.38, 0.38],
    [0.21, 0.21, 0.21], [0.10, 0.10, 0.10], [0.03, 0.03, 0.03],
]).reshape(4, 6, 3)


def chart_image():
    return np.repeat(np.repeat(CHART, PATCH, axis=0), PATCH, axis=1)


def srgb(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * x ** (1 / 2.4) - 0.055)


def main():
    t0 = time.time()
    img = chart_image()
    results = []
    fig, axes = plt.subplots(2, len(CONFIGS), figsize=(3.1 * len(CONFIGS), 6.4))

    for k, (name, kw) in enumerate(CONFIGS.items()):
        if kw is None:
            Mn = np.eye(3)
            C, gain = np.eye(3), np.ones(3)
        else:
            sim = Simulator(PixelStack(**BASE, **kw), verbose=False)
            res = sim.spectral_response(WL, ircf=True)
            Mx = color_mixing_matrix(res)
            C, gain = ccm_noise_gain(Mx)
            Mn = Mx / Mx.sum(1)[:, None]

        # sensor raw (already white balanced by construction: rows of Mn sum to 1)
        raw = img @ Mn.T
        e = np.clip(raw, 0, None) * SIGNAL_E
        noisy = rng.poisson(e) + rng.normal(0, READ_E, e.shape)
        noisy = noisy / SIGNAL_E
        out = noisy @ C.T

        # noise measured on the mid-grey patch (row 3, col 1)
        r0, c0 = 3 * PATCH, 1 * PATCH
        patch = out[r0 + 8:r0 + PATCH - 8, c0 + 8:c0 + PATCH - 8]
        sigma = patch.std(axis=(0, 1)) * SIGNAL_E
        sat = np.abs(raw - raw.mean(axis=2, keepdims=True)).mean()

        axes[0, k].imshow(srgb(raw))
        axes[0, k].set_title("%s\nraw (uncorrected)" % name, fontsize=8)
        axes[1, k].imshow(srgb(out))
        axes[1, k].set_title("after CCM  gain R/G/B = %.2f/%.2f/%.2f\n"
                             "noise sigma = %.0f/%.0f/%.0f e-"
                             % (gain[0], gain[1], gain[2],
                                sigma[0], sigma[1], sigma[2]), fontsize=8)
        for a in (axes[0, k], axes[1, k]):
            a.set_xticks([]); a.set_yticks([]); a.grid(False)

        results.append((name, Mn, C, gain, sigma, sat))

    fig.suptitle("Crosstalk desaturates the raw image; restoring colour with a "
                 "CCM amplifies noise\n(%.0f e- mid-grey signal, %.0f e- read noise)"
                 % (SIGNAL_E, READ_E), fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "fig6_image.png")
    plt.close(fig)

    with open(OUT / "ccm_noise.csv", "w", encoding="utf-8") as f:
        f.write("config,purity_R,purity_G,purity_B,ccm_gain_R,ccm_gain_G,"
                "ccm_gain_B,sigma_R_e,sigma_G_e,sigma_B_e,raw_saturation\n")
        for name, Mn, C, gain, sigma, sat in results:
            f.write("%s,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%.1f,%.1f,%.1f,%.4f\n"
                    % (name, Mn[0, 0], Mn[1, 1], Mn[2, 2],
                       gain[0], gain[1], gain[2], sigma[0], sigma[1], sigma[2], sat))

    print("%-22s%9s%9s%9s%10s%10s%10s" % ("config", "purR", "purG", "purB",
                                          "sigR[e-]", "sigG[e-]", "sigB[e-]"))
    for name, Mn, C, gain, sigma, sat in results:
        print("%-22s%9.3f%9.3f%9.3f%10.1f%10.1f%10.1f"
              % (name, Mn[0, 0], Mn[1, 1], Mn[2, 2], sigma[0], sigma[1], sigma[2]))
    print("\n%.1f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
