"""Compare saved Meep FDTD optical results with the local scalar BPM model.

The Meep archive stores every geometry argument used for the run.  This script
reconstructs that exact PixelStack, runs BPM at the exported grid spacing, and
compares total absorbed QE, the per-pixel optical split, and the normalised
depth profile.  Meep uses a reflecting oxide DTI while BPM can only bracket it
with an absorbing trench and an optically open boundary, so both BPM limits are
reported.

Outputs: out/meep_bpm_comparison.csv, out/fig18_meep_bpm_comparison.png,
out/fig19_meep_bpm_convergence.png
"""
from __future__ import annotations

import csv
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from bxsim import PixelStack, optics

MEEP_OUT = ROOT / "meep" / "out"
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)


def stack_from_args(a, dti_blocks_light):
    """Reconstruct the optical subset of PixelStack from a Meep args dict."""
    return PixelStack(
        pitch_um=float(a["pitch"]),
        n_pix=int(a["cell_pixels"]),
        ml_sag_um=float(a["ml_sag"]),
        ml_roc_override_um=a.get("ml_roc"),
        ml_shift_um=float(a.get("ml_shift", 0.0)),
        t_ml_to_cfa_um=float(a["t_ml_to_cfa"]),
        t_ircf_um=float(a.get("t_ircf", 0.0)),
        n_ircf=float(a.get("n_ircf", 1.65)),
        t_cfa_um=float(a["t_cfa"]),
        t_cfa_to_si_um=float(a["t_cfa_to_si"]),
        cfa_grid_enabled=float(a.get("cfa_grid_width", 0.0)) > 0,
        cfa_grid_width_um=float(a.get("cfa_grid_width", 0.15)),
        n_cfa_grid=float(a.get("n_cfa_grid", 1.25)),
        si_thickness_um=float(a["si_thickness"]),
        d_arc_um=float(a["d_arc"]),
        dti_enabled=float(a.get("dti_depth", 0.0)) > 0,
        dti_depth_um=float(a.get("dti_depth", 0.0)),
        dti_width_um=float(a.get("dti_width", 0.1)),
        dti_blocks_light=dti_blocks_light,
        dx_opt_nm=float(a["out_dx_nm"]),
        dz_opt_nm=float(a["out_dz_nm"]),
        dx_diff_nm=float(a["out_dx_nm"]),
        dz_diff_nm=float(a["out_dz_nm"]),
    )


def pixel_split(G, n):
    """Integrate a generation cube into an n by n physical pixel grid."""
    image = G.sum(axis=0)
    ny, nx = image.shape
    if nx % n or ny % n:
        raise ValueError("generation grid is not divisible by cell count")
    sx, sy = nx // n, ny // n
    per_pixel = np.empty((n, n))
    for r in range(n):
        for c in range(n):
            per_pixel[r, c] = image[r * sy:(r + 1) * sy,
                                    c * sx:(c + 1) * sx].sum()
    return per_pixel / per_pixel.sum()


def profile_similarity(a, b):
    """Cosine similarity after normalising both non-negative profiles."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a = a / max(a.sum(), 1e-30)
    b = b / max(b.sum(), 1e-30)
    return float(np.dot(a, b) / max(np.linalg.norm(a) * np.linalg.norm(b), 1e-30))


def fmt_split(split):
    return ";".join(",".join("%.8g" % x for x in row) for row in split)


def main():
    paths = sorted(MEEP_OUT.glob("fdtd_*.npz"))
    if not paths:
        raise SystemExit("no Meep .npz files found under meep/out")

    cache = {}
    rows = []
    detailed = {}
    for path in paths:
        d = np.load(path, allow_pickle=True)
        args = d["args"].item()
        # Old smoke files predate the corrected raw/asymmetry output.  Keep the
        # data visible but mark it as legacy instead of silently discarding it.
        corrected = "split_raw" in d.files and "asym" in d.files
        key_fields = (
            "wavelength", "cell_pixels", "pitch", "ml_sag", "ml_roc",
            "ml_shift", "t_ml_to_cfa", "t_ircf", "n_ircf", "t_cfa",
            "t_cfa_to_si", "cfa_grid_width", "n_cfa_grid", "d_arc",
            "si_thickness", "dti_depth", "dti_width", "out_dx_nm",
            "out_dz_nm", "cra", "aperture",
        )
        key = tuple(args.get(k) for k in key_fields)
        if key not in cache:
            aperture = args.get("aperture", "center")
            local = {}
            for mode, blocks in (("absorbing", True), ("open", False)):
                st = stack_from_args(args, blocks)
                G = optics.generation(
                    st, float(args["wavelength"]),
                    cra_deg=float(args.get("cra", 0.0)), aperture=aperture)
                # For full-plane illumination G contains n**2 equivalent
                # pixels, while QE is conventionally quoted per illuminated
                # area.  Centre-aperture G already represents one pixel.
                qe = float(G.sum())
                if aperture == "all":
                    qe /= st.n_pix ** 2
                local[mode] = dict(
                    G=G, qe=qe,
                    split=pixel_split(G, st.n_pix),
                    depth=G.sum(axis=(1, 2)),
                )
            cache[key] = local
        local = cache[key]

        Gm = np.asarray(d["G"], float)
        split_m = np.asarray(d["split"], float)
        n = int(args["cell_pixels"])
        c = n // 2
        is_center = args.get("aperture", "center") == "center"
        xt_m = 1.0 - split_m[c, c] if is_center else float("nan")
        depth_m = Gm.sum(axis=(1, 2))
        row = dict(
            file=path.name,
            corrected_output=corrected,
            resolution=int(args["resolution"]),
            pitch_um=float(args["pitch"]),
            wavelength_nm=float(args["wavelength"]),
            aperture=args.get("aperture", "center"),
            meep_qe=float(d["qe"]),
            bpm_absorbing_qe=local["absorbing"]["qe"],
            bpm_open_qe=local["open"]["qe"],
            meep_xt_pct=100 * xt_m,
            bpm_absorbing_xt_pct=(100 * (1 - local["absorbing"]["split"][c, c])
                                  if is_center else float("nan")),
            bpm_open_xt_pct=(100 * (1 - local["open"]["split"][c, c])
                             if is_center else float("nan")),
            split_l1_vs_absorbing=float(np.abs(split_m - local["absorbing"]["split"]).sum()),
            split_l1_vs_open=float(np.abs(split_m - local["open"]["split"]).sum()),
            depth_cosine_vs_absorbing=profile_similarity(depth_m, local["absorbing"]["depth"]),
            depth_cosine_vs_open=profile_similarity(depth_m, local["open"]["depth"]),
            meep_asym=float(d["asym"]) if "asym" in d.files else float("nan"),
            meep_split=fmt_split(split_m),
            bpm_absorbing_split=fmt_split(local["absorbing"]["split"]),
            bpm_open_split=fmt_split(local["open"]["split"]),
        )
        rows.append(row)
        detailed[path.name] = dict(meep_G=Gm, meep_split=split_m,
                                   args=args, local=local)

    csv_path = OUT / "meep_bpm_comparison.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    # Use the highest-resolution corrected 3 um case for spatial plots.
    candidates = [r for r in rows if r["corrected_output"] and r["pitch_um"] == 3.0]
    focus_row = max(candidates, key=lambda r: r["resolution"])
    focus = detailed[focus_row["file"]]
    args = focus["args"]

    fig = plt.figure(figsize=(13.2, 7.8))
    gs = fig.add_gridspec(2, 4, width_ratios=(1, 1, 1, 1.25))

    splits = [
        (focus["meep_split"], "Meep FDTD"),
        (focus["local"]["absorbing"]["split"], "BPM: absorbing DTI"),
        (focus["local"]["open"]["split"], "BPM: optically open"),
    ]
    vmax = max(float(s.max()) for s, _ in splits)
    for col, (split, title) in enumerate(splits):
        ax = fig.add_subplot(gs[0, col])
        ax.imshow(split * 100, cmap="magma", vmin=0, vmax=vmax * 100)
        for r in range(split.shape[0]):
            for c in range(split.shape[1]):
                ax.text(c, r, "%.3f" % (split[r, c] * 100), ha="center",
                        va="center", fontsize=7,
                        color="white" if split[r, c] < 0.5 * vmax else "black")
        ax.set_title(title + "\nabsorbed-power split [%]")
        ax.set_xlabel("pixel x offset")
        ax.set_ylabel("pixel y offset")
        n = split.shape[0]
        h = n // 2
        ax.set_xticks(range(n), range(-h, h + 1))
        ax.set_yticks(range(n), range(-h, h + 1))
        ax.grid(False)

    ax = fig.add_subplot(gs[0, 3])
    labels = [r["file"].replace("fdtd_550nm_center_", "") for r in rows]
    y = np.arange(len(rows))
    ax.scatter([r["meep_qe"] * 100 for r in rows], y, label="Meep", marker="o")
    ax.scatter([r["bpm_absorbing_qe"] * 100 for r in rows], y,
               label="BPM absorbing", marker="s")
    ax.scatter([r["bpm_open_qe"] * 100 for r in rows], y,
               label="BPM open", marker="^")
    ax.set_yticks(y, labels, fontsize=7)
    ax.set_xlabel("absorbed QE [%]")
    ax.set_title("Absolute absorption")
    ax.legend(fontsize=7)

    ax = fig.add_subplot(gs[1, :2])
    z = (np.arange(focus["meep_G"].shape[0]) + 0.5) * float(args["out_dz_nm"]) * 1e-3
    curves = [
        (focus["meep_G"].sum(axis=(1, 2)), "Meep"),
        (focus["local"]["absorbing"]["depth"], "BPM absorbing"),
        (focus["local"]["open"]["depth"], "BPM open"),
    ]
    for p, label in curves:
        ax.plot(z, p / p.sum(), label=label)
    ax.set_xlabel("depth in Si [um]")
    ax.set_ylabel("normalised absorption per depth bin")
    ax.set_title("Depth profile: %s" % focus_row["file"])
    ax.legend(fontsize=8)

    ax = fig.add_subplot(gs[1, 2:])
    corrected_rows = [r for r in rows if r["corrected_output"] and r["aperture"] == "center"]
    x = np.arange(len(corrected_rows))
    width = 0.26
    ax.bar(x - width, [r["meep_xt_pct"] for r in corrected_rows], width,
           label="Meep")
    ax.bar(x, [r["bpm_absorbing_xt_pct"] for r in corrected_rows], width,
           label="BPM absorbing")
    ax.bar(x + width, [r["bpm_open_xt_pct"] for r in corrected_rows], width,
           label="BPM open")
    ax.set_xticks(x, [r["file"].replace("fdtd_550nm_center_", "")
                      for r in corrected_rows], rotation=15, ha="right")
    ax.set_ylabel("optical crosstalk [%]")
    ax.set_title("Per-pixel split")
    ax.legend(fontsize=8)

    fig.suptitle(
        "Meep FDTD vs local BPM, reconstructed from saved run arguments\n"
        "Meep has reflecting oxide DTI; BPM absorbing/open curves bracket different physics",
        y=0.995)
    fig.tight_layout()
    fig.savefig(OUT / "fig18_meep_bpm_comparison.png", dpi=150)
    plt.close(fig)

    # Dedicated apples-to-apples convergence view.  These runs deliberately
    # remove DTI and the CFA grid so both solvers describe the same dielectric
    # geometry; remaining differences are discretisation and full-wave versus
    # scalar/one-way physics.
    validation = sorted(
        (r for r in rows if "validation_r" in r["file"] and "nodti" in r["file"]
         and r["aperture"] == "center"),
        key=lambda r: r["resolution"])
    if validation:
        fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
        res = [r["resolution"] for r in validation]
        bpm_qe = validation[-1]["bpm_open_qe"] * 100
        bpm_xt = validation[-1]["bpm_open_xt_pct"]

        axes[0].plot(res, [r["meep_qe"] * 100 for r in validation], "o-",
                     label="Meep FDTD")
        axes[0].axhline(bpm_qe, color="#d62728", ls="--", label="local BPM")
        axes[0].set_xlabel("Meep resolution [pixels/um]")
        axes[0].set_ylabel("absorbed QE [%]")
        axes[0].set_title("Absolute absorption")
        axes[0].legend(fontsize=8)

        axes[1].plot(res, [r["meep_xt_pct"] for r in validation], "o-",
                     label="Meep FDTD")
        axes[1].axhline(bpm_xt, color="#d62728", ls="--", label="local BPM")
        axes[1].set_xlabel("Meep resolution [pixels/um]")
        axes[1].set_ylabel("optical crosstalk [%]")
        axes[1].set_title("Per-pixel absorbed-power split")
        axes[1].legend(fontsize=8)

        fig.suptitle("Matched 0.8 um dielectric benchmark, 550 nm, normal incidence, no DTI/grid")
        fig.tight_layout()
        fig.savefig(OUT / "fig19_meep_bpm_convergence.png", dpi=150)
        plt.close(fig)

    print("%-30s %4s %9s %9s %9s %9s %9s %9s" %
          ("file", "res", "M QE", "BPMabs", "BPMopen", "M XT", "BPMabs", "BPMopen"))
    for r in rows:
        print("%-30s %4d %8.2f%% %8.2f%% %8.2f%% %8.3f%% %8.3f%% %8.3f%%" %
              (r["file"], r["resolution"], r["meep_qe"] * 100,
               r["bpm_absorbing_qe"] * 100, r["bpm_open_qe"] * 100,
               r["meep_xt_pct"], r["bpm_absorbing_xt_pct"],
               r["bpm_open_xt_pct"]))
    print("wrote", csv_path)
    print("wrote", OUT / "fig18_meep_bpm_comparison.png")
    if validation:
        print("wrote", OUT / "fig19_meep_bpm_convergence.png")


if __name__ == "__main__":
    main()
