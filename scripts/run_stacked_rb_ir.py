"""R+B stacked visible-cut filter over the K/IR pixels.

The current 3 um RGB-IR structure is used.  RGB source cells retain the
0.90 um CFA plus 0.30 um on-chip IR-cut geometry.  A K source cell instead
contains one 0.90 um R layer and one 0.90 um B layer, for a 1.80 um CFA stack
and a 2.10 um microlens-to-Si distance.  Its spectral transmission is T_R*T_B.

This is a source-cell approximation: the optical kernel depends on whether
light entered an RGB or K cell, while the lateral height step at the boundary
is not resolved.  Outputs: out/fig17_stacked_rb_ir.png,
out/stacked_rb_ir.csv.
"""
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bxsim import PixelStack, Simulator, materials as M

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)

PATTERN = ["RGRG", "GBGB", "RGKK", "GBKK"]
K_POSITIONS = [(r, c) for r in range(4) for c in range(4)
               if PATTERN[r][c] == "K"]
PROBE_WL = np.array([450.0, 550.0, 650.0, 850.0, 940.0])
PLOT_WL = np.arange(400.0, 1001.0, 5.0)
CRAS = (0.0, 30.0)
F_NUMBER = 1.8
N_SAMPLES = 8

STACK = dict(
    pitch_um=3.0, n_pix=3, si_thickness_um=6.0,
    pd_depth_um=3.0, pd_fill=1.00,
    dti_enabled=True, dti_depth_um=6.0, dti_width_um=0.20,
    ml_sag_um=0.80, t_ml_to_cfa_um=0.10,
    t_cfa_um=0.90, t_k_cfa_um=1.80,
    t_cfa_to_si_um=0.20, t_ircf_um=0.30,
    cfa_grid_enabled=True, cfa_grid_width_um=0.15,
    dx_opt_nm=50.0, dz_opt_nm=50.0,
    dx_diff_nm=100.0, dz_diff_nm=100.0,
)


def old_k_transmittance(wl):
    """Existing assumed black IR-pass K filter, for comparison."""
    wl = np.asarray(wl, float)
    return 0.90 / (1.0 + np.exp(-(wl - 780.0) / 22.0))


def source_color(target_pos, offset):
    """CFA source at target-offset, matching the kernel convention."""
    r, c = target_pos
    i, j = offset
    return PATTERN[(r - i) % 4][(c - j) % 4]


def pixel_response(target_pos, k_rgb, k_k, transmissions):
    """Response of one K-position PD to a spatially uniform scene."""
    half = k_rgb.shape[0] // 2
    total = 0.0
    parts = {c: 0.0 for c in "RGBK"}
    for i in range(-half, half + 1):
        for j in range(-half, half + 1):
            color = source_color(target_pos, (i, j))
            kernel = k_k if color == "K" else k_rgb
            value = transmissions[color] * kernel[i + half, j + half]
            total += value
            parts[color] += value
    return total, parts


def main():
    t0 = time.time()
    st = PixelStack(**STACK)
    sim = Simulator(st, verbose=False)
    rows = []
    results = {}

    for cra in CRAS:
        for wl in PROBE_WL:
            # The legacy/common kernel has the RGB stack height.  The K kernel
            # replaces RGB-only IRCF with the full 1.80 um R+B stack.
            k_base = sim.kernel(wl, cra_deg=cra, f_number=F_NUMBER,
                                n_samples=N_SAMPLES)
            k_stacked = sim.kernel(wl, cra_deg=cra, f_number=F_NUMBER,
                                   n_samples=N_SAMPLES, source_color="K")
            h = k_base.shape[0] // 2
            xt_base = 1.0 - k_base[h, h] / k_base.sum()
            xt_stacked = 1.0 - k_stacked[h, h] / k_stacked.sum()

            rgb_t = {c: float(M.cfa_transmittance(wl, c, nir_leak=True)
                              * (M.ircf_transmittance(wl) / 0.97))
                     for c in "RGB"}
            t_old = float(old_k_transmittance(wl))
            t_rb = float(M.stacked_cfa_transmittance(wl, ("R", "B")))
            trans_old = dict(rgb_t, K=t_old)
            trans_rb = dict(rgb_t, K=t_rb)

            old_resp, rb_resp = [], []
            rb_visible_from_k = []
            for pos in K_POSITIONS:
                v_old, _ = pixel_response(pos, k_base, k_base, trans_old)
                v_rb, p_rb = pixel_response(pos, k_base, k_stacked, trans_rb)
                old_resp.append(v_old)
                rb_resp.append(v_rb)
                rb_visible_from_k.append(p_rb["K"])

            row = dict(
                cra_deg=cra, wavelength_nm=wl,
                rgb_stack_um=st.stack_height_um,
                stacked_k_stack_um=st.stack_height_for("K"),
                k_trans_old=t_old, k_trans_rb=t_rb,
                xt_old_pct=100 * xt_base,
                xt_stacked_pct=100 * xt_stacked,
                xt_delta_pp=100 * (xt_stacked - xt_base),
                k_response_old_mean=float(np.mean(old_resp)),
                k_response_rb_mean=float(np.mean(rb_resp)),
                k_response_rb_min=float(np.min(rb_resp)),
                k_response_rb_max=float(np.max(rb_resp)),
                k_direct_rb_mean=float(np.mean(rb_visible_from_k)),
            )
            rows.append(row)
            results[(cra, wl)] = dict(base=k_base, stacked=k_stacked,
                                      old=np.array(old_resp), rb=np.array(rb_resp))
        print("CRA %.0f complete [%.1f s]" % (cra, time.time() - t0))

    header = list(rows[0])
    with open(OUT / "stacked_rb_ir.csv", "w", encoding="utf-8") as f:
        f.write(",".join(header) + "\n")
        for row in rows:
            f.write(",".join("%.8g" % row[k] for k in header) + "\n")

    t_old_plot = old_k_transmittance(PLOT_WL)
    t_rb_plot = M.stacked_cfa_transmittance(PLOT_WL, ("R", "B"))
    fig, axes = plt.subplots(2, 2, figsize=(12.4, 8.2))

    ax = axes[0, 0]
    ax.semilogy(PLOT_WL, np.maximum(t_old_plot, 1e-7), label="old assumed K")
    ax.semilogy(PLOT_WL, np.maximum(t_rb_plot, 1e-7), label="R x B stack")
    ax.axvspan(400, 700, color="#ffd54f", alpha=0.12, label="visible")
    ax.set_ylim(1e-7, 1.1)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("K-filter transmittance")
    ax.set_title("Visible rejection and IR throughput")
    ax.legend(fontsize=8)

    ax = axes[0, 1]
    for cra, color in zip(CRAS, ("#1f77b4", "#d62728")):
        old = [next(r for r in rows if r["cra_deg"] == cra and
                    r["wavelength_nm"] == wl)["xt_old_pct"] for wl in PROBE_WL]
        rb = [next(r for r in rows if r["cra_deg"] == cra and
                   r["wavelength_nm"] == wl)["xt_stacked_pct"] for wl in PROBE_WL]
        ax.plot(PROBE_WL, old, "--o", color=color, label="%.0f deg, old height" % cra)
        ax.plot(PROBE_WL, rb, "-o", color=color, label="%.0f deg, stacked" % cra)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("K-source spatial crosstalk [%]")
    ax.set_title("Geometry penalty from the thicker K stack")
    ax.legend(fontsize=7)

    ax = axes[1, 0]
    for cra, color in zip(CRAS, ("#1f77b4", "#d62728")):
        old = [next(r for r in rows if r["cra_deg"] == cra and
                    r["wavelength_nm"] == wl)["k_response_old_mean"] * 100
               for wl in PROBE_WL]
        rb = [next(r for r in rows if r["cra_deg"] == cra and
                   r["wavelength_nm"] == wl)["k_response_rb_mean"] * 100
              for wl in PROBE_WL]
        ax.semilogy(PROBE_WL, np.maximum(old, 1e-5), "--o", color=color,
                    label="%.0f deg, old K" % cra)
        ax.semilogy(PROBE_WL, np.maximum(rb, 1e-5), "-o", color=color,
                    label="%.0f deg, R x B" % cra)
    ax.set_ylim(1e-4, 100)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("mean K-pixel response [%]")
    ax.set_title("Flat-field K response, including neighbours")
    ax.legend(fontsize=7)

    ax = axes[1, 1]
    cra = 30.0
    for idx, pos in enumerate(K_POSITIONS):
        vals = [results[(cra, wl)]["rb"][idx] * 100 for wl in PROBE_WL]
        ax.semilogy(PROBE_WL, np.maximum(vals, 1e-5), "-o",
                    label="K(%d,%d)" % pos)
    ax.set_ylim(1e-4, 100)
    ax.set_xlabel("wavelength [nm]")
    ax.set_ylabel("K-pixel response [%]")
    ax.set_title("Four K positions, stacked R x B, CRA 30 deg")
    ax.legend(fontsize=8)

    fig.suptitle(
        "3.0 um RGB-IR pixel: 0.90 um R + 0.90 um B visible-cut stack over K\n"
        "RGB height %.2f um, K height %.2f um, f/%.1f, full-depth DTI"
        % (st.stack_height_um, st.stack_height_for("K"), F_NUMBER),
        y=0.995)
    fig.tight_layout()
    fig.savefig(OUT / "fig17_stacked_rb_ir.png", dpi=150)
    plt.close(fig)

    print("\n%-5s %-5s %10s %10s %10s %10s %10s" %
          ("CRA", "wl", "T_RxB", "XT old", "XT stack", "dXT", "K resp"))
    for row in rows:
        print("%5.0f %5.0f %10.4g %9.3f%% %9.3f%% %+9.3f %9.3f%%" %
              (row["cra_deg"], row["wavelength_nm"], row["k_trans_rb"],
               row["xt_old_pct"], row["xt_stacked_pct"], row["xt_delta_pp"],
               row["k_response_rb_mean"] * 100))
    print("\n%.1f s, wrote %s" % (time.time() - t0, OUT))


if __name__ == "__main__":
    main()
