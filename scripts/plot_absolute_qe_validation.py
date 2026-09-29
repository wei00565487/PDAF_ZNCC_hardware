"""Summarise the matched Meep/BPM absolute-QE benchmark.

The figure separates full-area stack transmission from the centre-only CFA
aperture.  A bare-Si convergence measurement supplies a transparent estimate
of the remaining r=60 mesh bias; it is an estimate, not a replacement for a
finer complete-stack run.
"""
from __future__ import annotations

import csv
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
sys.path.insert(0, str(ROOT))

from bxsim import diffusion, optics  # noqa: E402
from scripts.compare_meep_bpm import stack_from_args  # noqa: E402

# Independent 550 nm, 3 um bare-Si slab benchmark from meep/_diag_slab.py.
SLAB_ANALYTIC = 0.5418
SLAB_MEEP_R60 = 0.5008


def load_rows():
    with open(OUT / "meep_bpm_comparison.csv", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def richardson_limit(resolution, qe):
    """Fit q(r)=q_inf+a/r**p exactly to the three matched centre runs."""
    r1, r2, r3 = map(float, resolution)
    q1, q2, q3 = map(float, qe)
    target = (q1 - q2) / (q2 - q3)
    fn = lambda p: ((r1 ** -p - r2 ** -p) /
                    (r2 ** -p - r3 ** -p) - target)
    p = brentq(fn, 0.05, 8.0)
    a = (q1 - q2) / (r1 ** -p - r2 ** -p)
    q_inf = q1 - a * r1 ** -p
    return q_inf, p


def main():
    rows = load_rows()
    center = sorted(
        (r for r in rows if "validation_r" in r["file"]
         and "nodti" in r["file"] and r["aperture"] == "center"),
        key=lambda r: int(r["resolution"]))
    all_row = next(r for r in rows if r["aperture"] == "all"
                   and "validation_r60_all" in r["file"])

    res = np.array([int(r["resolution"]) for r in center])
    meep_center = np.array([float(r["meep_qe"]) for r in center])
    bpm_center = float(center[-1]["bpm_open_qe"])
    meep_all = float(all_row["meep_qe"])
    bpm_all = float(all_row["bpm_open_qe"])

    slab_ratio = SLAB_MEEP_R60 / SLAB_ANALYTIC
    all_mesh_corrected = meep_all / slab_ratio
    center_mesh_corrected = meep_center[-1] / slab_ratio
    center_extrapolated, order = richardson_limit(res, meep_center)
    estimate_lo, estimate_hi = sorted((center_mesh_corrected, center_extrapolated))

    bpm_retention = bpm_center / bpm_all
    meep_retention = meep_center[-1] / meep_all
    estimated_retention = center_extrapolated / all_mesh_corrected
    center_scale_lo = estimate_lo / bpm_center
    center_scale_hi = estimate_hi / bpm_center

    # Feed both optical generation cubes into one identical 3D carrier model.
    meep_path = ROOT / "meep" / "out" / center[-1]["file"]
    meep_data = np.load(meep_path, allow_pickle=True)
    args = meep_data["args"].item()
    stack = stack_from_args(args, dti_blocks_light=False)
    u = diffusion.collection_map(stack)
    bpm_G = optics.generation(stack, float(args["wavelength"]),
                              cra_deg=float(args.get("cra", 0.0)), aperture="center")
    K_bpm = diffusion.collect(bpm_G, u, stack)
    K_meep = diffusion.collect(np.asarray(meep_data["G"], float), u, stack)
    c = stack.n_pix // 2
    bpm_external = float(K_bpm.sum())
    meep_external_r60 = float(K_meep.sum())
    meep_external_lo = meep_external_r60 * estimate_lo / meep_center[-1]
    meep_external_hi = meep_external_r60 * estimate_hi / meep_center[-1]
    bpm_col_eff = bpm_external / bpm_center
    meep_col_eff = meep_external_r60 / meep_center[-1]
    bpm_total_xt = 1.0 - float(K_bpm[c, c] / K_bpm.sum())
    meep_total_xt = 1.0 - float(K_meep[c, c] / K_meep.sum())

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5))

    ax = axes[0]
    ax.plot(res, meep_center * 100, "o-", lw=2, label="Meep, centre aperture")
    ax.axhline(bpm_center * 100, color="#d62728", ls="--", label="BPM, centre aperture")
    ax.axhspan(estimate_lo * 100, estimate_hi * 100, color="#1f77b4", alpha=0.16,
               label="provisional Meep limit")
    ax.scatter([60], [meep_all * 100], marker="s", s=65, color="#2ca02c",
               label="Meep r60, all clear")
    ax.scatter([60], [bpm_all * 100], marker="^", s=70, color="#9467bd",
               label="BPM, all clear")
    ax.scatter([64], [all_mesh_corrected * 100], marker="D", s=55,
               facecolors="none", edgecolors="#2ca02c",
               label="all clear, slab mesh corrected")
    ax.set_xlabel("Meep resolution [pixels/um]")
    ax.set_ylabel("absorbed QE [%]")
    ax.set_title("Absolute absorption at 550 nm")
    ax.set_ylim(25, 86)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=7.5, loc="lower right")

    ax = axes[1]
    labels = ["BPM", "Meep r60", "Meep estimate"]
    vals = np.array([bpm_retention, meep_retention, estimated_retention]) * 100
    colors = ["#d62728", "#1f77b4", "#6baed6"]
    bars = ax.bar(labels, vals, color=colors)
    for bar, value in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width()/2, value + 0.7, f"{value:.1f}%",
                ha="center", va="bottom")
    ax.set_ylim(0, 100)
    ax.set_ylabel("centre / all-clear QE [%]")
    ax.set_title("Transmission retained by centre aperture")
    ax.grid(axis="y", alpha=0.25)

    fig.suptitle("Matched 3D Meep FDTD vs scalar BPM: absolute-QE budget")
    fig.tight_layout()
    fig_path = OUT / "fig20_absolute_qe_validation.png"
    fig.savefig(fig_path, dpi=170)
    plt.close(fig)

    # Final external QE after the shared carrier-collection model.
    fig, ax = plt.subplots(figsize=(7.6, 4.5))
    labels = ["BPM", "Meep r60", "Meep estimate"]
    absorbed = np.array([bpm_center, meep_center[-1],
                         0.5 * (estimate_lo + estimate_hi)]) * 100
    collected = np.array([bpm_external, meep_external_r60,
                          0.5 * (meep_external_lo + meep_external_hi)]) * 100
    x = np.arange(3)
    width = 0.34
    b1 = ax.bar(x - width/2, absorbed, width, label="absorbed optical QE")
    b2 = ax.bar(x + width/2, collected, width, label="collected external QE")
    for bars in (b1, b2):
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.7,
                    f"{bar.get_height():.1f}%", ha="center", fontsize=8)
    ax.errorbar(x[2] + width/2, collected[2],
                yerr=[[collected[2] - meep_external_lo*100],
                      [meep_external_hi*100 - collected[2]]],
                fmt="none", color="black", capsize=4)
    ax.set_xticks(x, labels)
    ax.set_ylabel("fraction of incident photons [%]")
    ax.set_ylim(0, 85)
    ax.set_title("550 nm absolute QE after the same 3D carrier model")
    ax.grid(axis="y", alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    ext_fig_path = OUT / "fig21_external_qe_validation.png"
    fig.savefig(ext_fig_path, dpi=170)
    plt.close(fig)

    metrics = [
        ("bpm_all_clear_qe", bpm_all, "direct"),
        ("meep_r60_all_clear_qe", meep_all, "direct"),
        ("meep_all_clear_mesh_corrected", all_mesh_corrected, "estimate"),
        ("bpm_center_qe", bpm_center, "direct"),
        ("meep_r60_center_qe", meep_center[-1], "direct"),
        ("meep_center_mesh_corrected", center_mesh_corrected, "estimate"),
        ("meep_center_richardson_limit", center_extrapolated, "estimate"),
        ("bpm_center_to_all_retention", bpm_retention, "direct"),
        ("meep_r60_center_to_all_retention", meep_retention, "direct"),
        ("meep_estimated_center_to_all_retention", estimated_retention, "estimate"),
        ("bpm_to_meep_center_scale_low", center_scale_lo, "estimate"),
        ("bpm_to_meep_center_scale_high", center_scale_hi, "estimate"),
        ("bpm_external_qe", bpm_external, "direct"),
        ("meep_r60_external_qe", meep_external_r60, "direct"),
        ("meep_external_qe_low", meep_external_lo, "estimate"),
        ("meep_external_qe_high", meep_external_hi, "estimate"),
        ("bpm_carrier_collection_efficiency", bpm_col_eff, "direct"),
        ("meep_r60_carrier_collection_efficiency", meep_col_eff, "direct"),
        ("bpm_total_crosstalk_after_transport", bpm_total_xt, "direct"),
        ("meep_r60_total_crosstalk_after_transport", meep_total_xt, "direct"),
        ("richardson_order", order, "fit"),
    ]
    csv_path = OUT / "absolute_qe_validation.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(("metric", "value", "status"))
        w.writerows(metrics)

    print(f"Meep all-clear r60: {meep_all:.6f}; mesh-corrected: {all_mesh_corrected:.6f}")
    print(f"Meep centre r60: {meep_center[-1]:.6f}; provisional limit: "
          f"{estimate_lo:.6f}..{estimate_hi:.6f}")
    print(f"centre/all retention BPM={bpm_retention:.6f}, Meep r60={meep_retention:.6f}")
    print(f"provisional BPM centre-QE scale: {center_scale_lo:.6f}..{center_scale_hi:.6f}")
    print(f"external QE BPM={bpm_external:.6f}, Meep r60={meep_external_r60:.6f}, "
          f"Meep estimate={meep_external_lo:.6f}..{meep_external_hi:.6f}")
    print(f"total XT after transport BPM={bpm_total_xt:.6f}, Meep r60={meep_total_xt:.6f}")
    print("wrote", csv_path)
    print("wrote", fig_path)
    print("wrote", ext_fig_path)


if __name__ == "__main__":
    main()
