"""Assemble optics + transport into Bayer crosstalk (mixed-color) figures."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import diffusion, materials as M, optics
from .stack import PixelStack

BAYER_CHANNELS = ("R", "Gr", "Gb", "B")
# position of each channel inside the 2x2 cell, with the center pixel = pattern[0]
_POS = {"R": (0, 0), "Gr": (0, 1), "Gb": (1, 0), "B": (1, 1)}


def planck(wl_nm, T=6500.0):
    """Relative spectral radiance of a blackbody (arbitrary scale)."""
    wl = np.asarray(wl_nm, float) * 1e-9
    h, c, kB = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    return (2 * h * c ** 2 / wl ** 5) / (np.exp(h * c / (wl * kB * T)) - 1.0)


class Simulator:
    """One geometry -> crosstalk kernels for any wavelength / angle / color."""

    def __init__(self, stack: PixelStack, verbose: bool = True):
        self.stack = stack
        self.verbose = verbose
        self._u = None
        self._u_ideal = None
        self._gcache = {}

    # -- transport -------------------------------------------------------
    @property
    def u(self):
        if self._u is None:
            if self.verbose:
                print("[bxsim] solving adjoint carrier-collection problem ...")
            self._u = diffusion.collection_map(self.stack, verbose=self.verbose)
        return self._u

    @property
    def u_ideal(self):
        """Hypothetical perfect transport: every carrier goes to its own pixel."""
        if self._u_ideal is None:
            s = self.stack
            x, y, z, dx, dz = s.diff_grid()
            X, Y = np.meshgrid(x, y)
            h = s.pitch_um / 2
            m = ((np.abs(X) < h) & (np.abs(Y) < h)).astype(float)
            self._u_ideal = np.repeat(m[None, :, :], len(z), axis=0)
        return self._u_ideal

    # -- kernels ---------------------------------------------------------
    def kernel(self, wl_nm: float, cra_deg: float = 0.0, azimuth_deg: float = 0.0,
               transport: str = "full", half: int | None = None,
               f_number: float | None = None, n_samples: int = 32,
               source_color: str | None = None):
        """Fraction of the photons entering ONE pixel's CFA cell that end up as
        signal in each neighbouring photodiode.  K[half, half] is the pixel's
        own photodiode.

        `f_number` switches from a single plane wave to the cone an f/N lens
        delivers around the chief ray (see optics.generation_cone).  A real
        sensor never sees a plane wave, so this is the realistic setting;
        f_number=None keeps the collimated case for comparison.
        """
        s = self.stack
        key = (round(wl_nm, 6), round(cra_deg, 6), round(azimuth_deg, 6),
               f_number, n_samples if f_number else 0,
               source_color.upper() if source_color else None)
        Gd = self._gcache.get(key)
        if Gd is None:
            if f_number is None:
                G = optics.generation(s, wl_nm, cra_deg, azimuth_deg,
                                      aperture="center", source_color=source_color)
            else:
                G = optics.generation_cone(s, wl_nm, f_number, cra_deg,
                                           azimuth_deg, aperture="center",
                                           n_samples=n_samples,
                                           source_color=source_color)
            fx = int(round(s.dx_diff_nm / s.dx_opt_nm))
            fz = int(round(s.dz_diff_nm / s.dz_opt_nm))
            Gd = optics.downsample(G, fx, fz)
            if len(self._gcache) < 512:
                self._gcache[key] = Gd
        u = self.u if transport == "full" else self.u_ideal
        return diffusion.collect(Gd, u, s, half=half)

    def kernel_spectrum(self, wavelengths, cra_deg=0.0, transport="full", half=None,
                        f_number=None, n_samples=32, source_color=None):
        return np.array([self.kernel(w, cra_deg, transport=transport, half=half,
                                     f_number=f_number, n_samples=n_samples,
                                     source_color=source_color)
                         for w in wavelengths])

    # -- channel responses ----------------------------------------------
    def channel_matrix(self, K, pattern="RGGB", nir_leak=True):
        """A[channel][source_color] = summed kernel weight, per wavelength.

        For a photodiode at Bayer position p, light that entered the CFA cell at
        position p-o contributes K[o]; that cell has color `pattern[p-o]`.
        """
        half = K.shape[-1] // 2
        s = self.stack
        A = {ch: {"R": 0.0, "G": 0.0, "B": 0.0} for ch in BAYER_CHANNELS}
        for ch in BAYER_CHANNELS:
            pi, pj = _POS[ch]
            for i in range(-half, half + 1):
                for j in range(-half, half + 1):
                    col = s.bayer_color(pi - i, pj - j, pattern)
                    A[ch][col] = A[ch][col] + K[..., i + half, j + half]
        return A

    def spectral_response(self, wavelengths, cra_deg=0.0, pattern="RGGB",
                          transport="full", ircf=True, nir_leak=True, half=None):
        """QE-like spectral response of each Bayer channel, with and without
        the spatial (optical + electrical) crosstalk."""
        wl = np.asarray(wavelengths, float)
        Ks = self.kernel_spectrum(wl, cra_deg, transport=transport, half=half)
        A = self.channel_matrix(Ks, pattern)
        T = {c: M.cfa_transmittance(wl, c, nir_leak) for c in "RGB"}
        F = M.ircf_transmittance(wl) if ircf else np.ones_like(wl)
        tot = Ks.reshape(len(wl), -1).sum(axis=1)

        resp, resp_nox = {}, {}
        for ch in BAYER_CHANNELS:
            own = self.stack.bayer_color(*_POS[ch], pattern)
            resp[ch] = F * sum(A[ch][c] * T[c] for c in "RGB")
            resp_nox[ch] = F * tot * T[own]        # same QE, zero spatial mixing
        return {"wl": wl, "K": Ks, "A": A, "resp": resp, "resp_no_xtalk": resp_nox,
                "qe_total": tot, "T": T, "ircf": F}


# ---------------------------------------------------------------------------
def color_mixing_matrix(res, illum_T=6500.0, pattern="RGGB"):
    """3x3 raw-channel mixing matrix under a blackbody illuminant.

    Rows = sensor channels (R, G, B; G = mean of Gr/Gb).
    Cols = the CFA color the light actually passed through.
    """
    wl = res["wl"]
    phi = planck(wl, illum_T)
    dwl = np.gradient(wl)
    A = res["A"]
    F = res["ircf"]
    T = res["T"]
    rows = {"R": ["R"], "G": ["Gr", "Gb"], "B": ["B"]}
    Mx = np.zeros((3, 3))
    for r, ch_name in enumerate("RGB"):
        acc = np.zeros(3)
        for ch in rows[ch_name]:
            for c, cc in enumerate("RGB"):
                acc[c] += float(np.sum(phi * F * A[ch][cc] * T[cc] * dwl))
        Mx[r] = acc / len(rows[ch_name])
    return Mx


def ccm_noise_gain(Mx):
    """White-balanced inverse of the mixing matrix and its per-channel noise gain."""
    wb = Mx.sum(axis=1)
    Mn = Mx / wb[:, None]              # each row sums to 1 (white -> [1,1,1])
    C = np.linalg.inv(Mn)
    return C, np.sqrt((C ** 2).sum(axis=1))
