"""Small deterministic functional checks for the dual-PD ZNCC reference."""

import pathlib
import sys
import importlib.util

import numpy as np

module_path = pathlib.Path(__file__).resolve().parents[1] / "bxsim" / "dual_pd_zncc.py"
spec = importlib.util.spec_from_file_location("dual_pd_zncc", module_path)
dual_pd_zncc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = dual_pd_zncc
spec.loader.exec_module(dual_pd_zncc)
DualPDStream = dual_pd_zncc.DualPDStream
zncc_tile = dual_pd_zncc.zncc_tile


def main() -> None:
    rng = np.random.default_rng(20260925)
    errors = []

    # Verify disparity sign, integer peak, subpixel output encoding and confidence.
    left = rng.integers(0, 4096, size=(32, 64), dtype=np.uint16)
    right = rng.integers(0, 4096, size=(32, 64), dtype=np.uint16)
    right[:, 4:] = left[:, :-4]
    result = zncc_tile(left, right, max_disparity=8)
    if abs(result.disparity_px - 4.0) > 0.1:
        errors.append(f"shift/sign: expected +4, got {result.disparity_px:.4f}")
    if result.disparity_q4_4 != 64:
        errors.append(f"Q4.4 encoding: expected 64, got {result.disparity_q4_4}")
    if result.confidence_u8 < 200:
        errors.append(f"confidence on strong match is low: {result.confidence_u8}")

    # Flat regions must not produce a valid-looking disparity.
    flat = zncc_tile(np.full((16, 32), 700), np.full((16, 32), 700), 4)
    if np.isfinite(flat.disparity_px) or flat.confidence_u8 != 0:
        errors.append("flat tile should return invalid disparity and zero confidence")

    # Exercise row streaming, tile boundaries, tags, and the 32x24 output count.
    width, height, tile_w, tile_h = 320, 240, 10, 10
    stream = DualPDStream(width, height, max_disparity=4)
    expected = rng.integers(0, 4096, size=(height, width), dtype=np.uint16)
    observed = rng.integers(0, 4096, size=(height, width), dtype=np.uint16)
    observed[:, 2:] = expected[:, :-2]
    outputs = []
    for y in range(height):
        outputs.extend(stream.push_row(expected[y], observed[y]))
    if len(outputs) != 32 * 24:
        errors.append(f"stream emitted {len(outputs)} results, expected 768")
    if outputs and (outputs[0][:2] != (0, 0) or outputs[-1][:2] != (23, 31)):
        errors.append("tile result tags are not in raster order")
    wrong = [(ty, tx, r.disparity_px) for ty, tx, r in outputs
             if not np.isfinite(r.disparity_px) or abs(r.disparity_px - 2.0) > 0.2]
    if wrong:
        errors.append(f"stream tile shift mismatch ({len(wrong)} tiles; first {wrong[0]})")

    # Matching R support is allowed to cross the tile's right boundary.
    left = rng.integers(0, 4096, size=(24, 32), dtype=np.uint16)
    right = rng.integers(0, 4096, size=(24, 32), dtype=np.uint16)
    right[:, 4:] = left[:, :-4]
    edge = zncc_tile(left, right, max_disparity=8, tile_bounds=(0, 24, 8, 16))
    if abs(edge.disparity_px - 4.0) > 0.1:
        errors.append(f"tile-crossing support: expected +4, got {edge.disparity_px:.4f}")
    left_mask = rng.random(left.shape) > 0.12
    right_mask = rng.random(right.shape) > 0.12
    masked = zncc_tile(left, right, max_disparity=8, tile_bounds=(0, 24, 8, 16),
                        left_mask=left_mask, right_mask=right_mask)
    if abs(masked.disparity_px - 4.0) > 0.1:
        errors.append(f"masked support: expected +4, got {masked.disparity_px:.4f}")

    # The four global CFA phases are independently centered. This pattern has
    # a phase-dependent black offset that a single all-pixel mean would mishandle.
    phase_l = rng.integers(0, 1024, size=(24, 32), dtype=np.uint16)
    phase_l[0::2, 0::2] += 0
    phase_l[0::2, 1::2] += 800
    phase_l[1::2, 0::2] += 1600
    phase_l[1::2, 1::2] += 2400
    phase_r = rng.integers(0, 1024, size=(24, 32), dtype=np.uint16)
    phase_r[:, 4:] = phase_l[:, :-4]
    parity = zncc_tile(phase_l, phase_r, max_disparity=8)
    if abs(parity.disparity_px - 4.0) > 0.1:
        errors.append(f"Bayer-phase centering: expected +4, got {parity.disparity_px:.4f}")

    if errors:
        raise SystemExit("FAIL\n" + "\n".join(errors))
    print("PASS: Bayer-phase ZNCC, 2-pixel disparity grid, ROI halo, masks, Q4.4 and 32x24 stream")


if __name__ == "__main__":
    main()
