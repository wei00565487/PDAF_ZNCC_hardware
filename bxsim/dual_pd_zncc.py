"""Streaming reference model for block based dual-pixel phase detection.

Input rows contain paired L/R samples in raster order. The frame is divided
into independent tiles; each tile is scored over a configurable horizontal
disparity range using zero-mean normalized cross correlation (ZNCC).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ZNCCResult:
    disparity_px: float
    score: float
    peak_score: float
    second_score: float

    @property
    def confidence(self) -> float:
        """Backward-compatible alias; score is uncalibrated, not a probability."""
        return self.score

    @property
    def disparity_q4_4(self) -> int:
        """Signed Q4.4 disparity code (1/16 pixel), saturated to 9 bits."""
        return int(np.clip(np.rint(self.disparity_px * 16.0), -256, 255))

    @property
    def confidence_u8(self) -> int:
        """Confidence mapped to the full unsigned 8-bit range."""
        return int(np.clip(np.rint(self.score * 255.0), 0, 255))


def zncc_tile(
    left: np.ndarray,
    right: np.ndarray,
    max_disparity: int = 16,
    *,
    tile_bounds: tuple[int, int, int, int] | None = None,
    left_mask: np.ndarray | None = None,
    right_mask: np.ndarray | None = None,
    min_pairs: int = 32,
    global_y_offset: int = 0,
) -> ZNCCResult:
    """Return Bayer-aware disparity and the repository's uncalibrated score.

    ``tile_bounds`` is ``(y0, y1, x0, x1)`` in the full-frame coordinate
    system. Only L coordinates are constrained to the ROI; corresponding R
    coordinates may cross its boundary, but are always clipped to the frame.
    Even-pixel shifts preserve CFA phase. Each of the four global CFA phases
    is independently mean-centered before phase covariances/energies are
    combined, matching ``pdaf.py`` in pdaf-afnet-study.
    """
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    if left.ndim != 2 or right.shape != left.shape:
        raise ValueError("left and right must be equally sized 2-D arrays")
    if max_disparity < 4 or max_disparity % 2:
        raise ValueError("max_disparity must be even and >= 4 sensor pixels")
    if min_pairs < 8:
        raise ValueError("min_pairs must be >= 8")
    h, w = left.shape
    y0, y1, x0, x1 = tile_bounds or (0, h, 0, w)
    if not (0 <= y0 < y1 <= h and 0 <= x0 < x1 <= w):
        raise ValueError("tile_bounds must be a nonempty in-frame half-open ROI")
    lm = np.isfinite(left)
    rm = np.isfinite(right)
    if left_mask is not None:
        if np.shape(left_mask) != left.shape:
            raise ValueError("left_mask shape mismatch")
        lm &= np.asarray(left_mask, dtype=bool)
    if right_mask is not None:
        if np.shape(right_mask) != right.shape:
            raise ValueError("right_mask shape mismatch")
        rm &= np.asarray(right_mask, dtype=bool)

    disparities = np.arange(-max_disparity, max_disparity + 1, 2)
    scores = np.full(disparities.size, np.nan, dtype=np.float64)
    counts = np.zeros(disparities.size, dtype=np.int64)
    for i, d in enumerate(disparities):
        yb, ye = max(y0, 0), min(y1, h)
        xb, xe = max(x0, -int(d)), min(x1, w - int(d))
        numerator = energy_l = energy_r = 0.0
        n = 0
        for py in range(2):
            for px in range(2):
                global_ys = yb + global_y_offset
                ys = yb + (py - global_ys) % 2
                xs = xb + (px - xb) % 2
                if ys >= ye or xs >= xe:
                    continue
                a = (slice(ys, ye, 2), slice(xs, xe, 2))
                b = (slice(ys, ye, 2), slice(xs + int(d), xe + int(d), 2))
                mask = lm[a] & rm[b]
                count = int(mask.sum())
                if count < 3:
                    continue
                lv = left[a][mask]
                rv = right[b][mask]
                lv = lv - lv.mean()
                rv = rv - rv.mean()
                numerator += float(lv @ rv)
                energy_l += float(lv @ lv)
                energy_r += float(rv @ rv)
                n += count
        counts[i] = n
        denom = np.sqrt(energy_l * energy_r)
        if n >= min_pairs and denom > n * 1e-12:
            scores[i] = numerator / denom

    finite = np.isfinite(scores)
    if finite.sum() < 3:
        return ZNCCResult(float("nan"), 0.0, float("nan"), float("nan"))
    best = int(np.nanargmax(scores))
    peak = float(scores[best])
    boundary = best in (0, len(scores) - 1)

    # The candidate spacing is two sensor pixels; clamp the fitted delta to
    # half that interval, as in pdaf.py.
    offset = 0.0
    curvature = 0.0
    if not boundary and np.isfinite(scores[best - 1:best + 2]).all():
        ym, y0, yp = scores[best - 1 : best + 2]
        curvature = float(2.0 * y0 - ym - yp)
        if curvature > 1e-12:
            offset = float(np.clip((ym - yp) / (2.0 * (ym - 2.0 * y0 + yp)), -0.5, 0.5) * 2.0)

    competing = scores.copy()
    competing[max(0, best - 1):min(len(scores), best + 2)] = np.nan
    second = float(np.nanmax(competing)) if np.isfinite(competing).any() else peak
    margin = max(0.0, peak - second)
    score = (float(np.clip(peak, 0.0, 1.0))
             * float(np.clip(margin / 0.25, 0.0, 1.0))
             * float(np.clip(curvature / 0.15, 0.0, 1.0))
             * min(1.0, counts[best] / 128.0))
    if boundary:
        score = 0.0
    return ZNCCResult(float(disparities[best]) + offset, score, peak, second)


class DualPDStream:
    """Consume one paired L/R raster row at a time and emit completed tiles.

    The reference model retains one vertical tile band in host memory. A
    hardware implementation can map this storage to a circular line SRAM.
    ``push_row`` yields ``(tile_row, tile_col, result)`` when a tile completes.
    """

    def __init__(
        self,
        width: int = 4000,
        height: int = 3000,
        pixel_pitch_um: float = 2.44,
        tile_cols: int = 32,
        tile_rows: int = 24,
        max_disparity: int = 16,
    ) -> None:
        if width % tile_cols or height % tile_rows:
            raise ValueError("frame dimensions must divide evenly into tile grid")
        if pixel_pitch_um <= 0:
            raise ValueError("pixel_pitch_um must be positive")
        self.width, self.height = width, height
        self.pixel_pitch_um = pixel_pitch_um
        self.active_width_mm = width * pixel_pitch_um / 1000.0
        self.active_height_mm = height * pixel_pitch_um / 1000.0
        self.tile_cols, self.tile_rows = tile_cols, tile_rows
        self.tile_w, self.tile_h = width // tile_cols, height // tile_rows
        self.max_disparity = max_disparity
        self._row_index = 0
        self._band_l = np.empty((self.tile_h, width), dtype=np.float64)
        self._band_r = np.empty_like(self._band_l)
        self._band_lmask = np.ones((self.tile_h, width), dtype=bool)
        self._band_rmask = np.ones_like(self._band_lmask)

    def push_row(self, left: np.ndarray, right: np.ndarray,
                 left_mask: np.ndarray | None = None,
                 right_mask: np.ndarray | None = None):
        """Push a row; return completed tile results, or an empty list."""
        if self._row_index >= self.height:
            raise RuntimeError("all frame rows have already been consumed")
        left = np.asarray(left)
        right = np.asarray(right)
        if left.shape != (self.width,) or right.shape != (self.width,):
            raise ValueError(f"each input row must have shape ({self.width},)")
        lm = np.isfinite(left)
        rm = np.isfinite(right)
        if left_mask is not None:
            if np.shape(left_mask) != left.shape:
                raise ValueError("left_mask row shape mismatch")
            lm &= np.asarray(left_mask, dtype=bool)
        if right_mask is not None:
            if np.shape(right_mask) != right.shape:
                raise ValueError("right_mask row shape mismatch")
            rm &= np.asarray(right_mask, dtype=bool)
        slot = self._row_index % self.tile_h
        self._band_l[slot] = left
        self._band_r[slot] = right
        self._band_lmask[slot] = lm
        self._band_rmask[slot] = rm
        completed = []
        if slot == self.tile_h - 1:
            tile_row = self._row_index // self.tile_h
            for col in range(self.tile_cols):
                x0, x1 = col * self.tile_w, (col + 1) * self.tile_w
                result = zncc_tile(
                    self._band_l,
                    self._band_r,
                    self.max_disparity,
                    tile_bounds=(0, self.tile_h, x0, x1),
                    left_mask=self._band_lmask,
                    right_mask=self._band_rmask,
                    global_y_offset=tile_row * self.tile_h,
                )
                completed.append((tile_row, col, result))
        self._row_index += 1
        return completed

    @property
    def rows_received(self) -> int:
        return self._row_index
