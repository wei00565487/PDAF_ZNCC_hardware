"""Optical constants for the pixel stack.

Silicon n / alpha are tabulated at 300 K and follow the widely used
"self-consistent optical parameters of intrinsic silicon at 300 K"
data set (M. A. Green, Sol. Energy Mater. Sol. Cells 92 (2008) 1305).
Values here are rounded; swap in a measured CSV via `load_si_csv()`
if you have vendor data.

Color filter transmittances are parametric (logistic band edges) and are
meant to be replaced by measured CFA curves when available -- the shape of
the NIR leak above ~700 nm matters a lot for red/NIR crosstalk.
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# Silicon
# --------------------------------------------------------------------------
_SI_WL_NM = np.array([
    400, 420, 440, 460, 480, 500, 520, 540, 560, 580, 600, 620, 640, 660,
    680, 700, 720, 740, 760, 780, 800, 850, 900, 950, 1000, 1050, 1100,
], dtype=float)

_SI_N = np.array([
    5.587, 5.045, 4.783, 4.640, 4.436, 4.297, 4.199, 4.123, 4.061, 4.010,
    3.969, 3.933, 3.902, 3.875, 3.851, 3.831, 3.813, 3.797, 3.782, 3.769,
    3.757, 3.731, 3.711, 3.694, 3.679, 3.667, 3.657,
], dtype=float)

# absorption coefficient [1/cm]
_SI_ALPHA_CM = np.array([
    9.52e4, 5.72e4, 3.55e4, 2.33e4, 1.62e4, 1.11e4, 8.62e3, 7.05e3, 6.02e3,
    5.06e3, 4.14e3, 3.49e3, 3.02e3, 2.62e3, 2.28e3, 1.90e3, 1.62e3, 1.39e3,
    1.19e3, 1.03e3, 8.50e2, 5.35e2, 3.06e2, 1.56e2, 6.40e1, 1.60e1, 1.00e0,
], dtype=float)

_si_wl_override = None
_si_n_override = None
_si_alpha_override = None


def load_si_csv(path: str) -> None:
    """Override the built-in Si table with `wavelength_nm,n,alpha_per_cm` CSV."""
    global _si_wl_override, _si_n_override, _si_alpha_override
    d = np.loadtxt(path, delimiter=",", skiprows=1)
    _si_wl_override, _si_n_override, _si_alpha_override = d[:, 0], d[:, 1], d[:, 2]


def _si_table():
    if _si_wl_override is None:
        return _SI_WL_NM, _SI_N, _SI_ALPHA_CM
    return _si_wl_override, _si_n_override, _si_alpha_override


def si_n(wl_nm):
    wl, n, _ = _si_table()
    return np.interp(wl_nm, wl, n)


def si_alpha_per_um(wl_nm):
    """Absorption coefficient in 1/um (log-interpolated: alpha spans 5 decades)."""
    wl, _, a = _si_table()
    return np.exp(np.interp(wl_nm, wl, np.log(a))) * 1e-4


def si_absorption_depth_um(wl_nm):
    return 1.0 / si_alpha_per_um(wl_nm)


def si_index_complex(wl_nm):
    """n + i*k with k = alpha*lambda/(4*pi)."""
    a_um = si_alpha_per_um(wl_nm)
    k = a_um * (wl_nm * 1e-3) / (4.0 * np.pi)
    return si_n(wl_nm) + 1j * k


# --------------------------------------------------------------------------
# Color filter array
# --------------------------------------------------------------------------
def _logi(x, x0, w):
    return 1.0 / (1.0 + np.exp(-(np.asarray(x, float) - x0) / w))


def cfa_transmittance(wl_nm, color: str, nir_leak: bool = True):
    """Parametric organic-dye CFA transmittance (0..1) for 'R', 'G', 'B', 'C'(clear)."""
    wl = np.asarray(wl_nm, float)
    c = color.upper()
    if c == "C":
        return np.full_like(wl, 0.95)
    if c == "B":
        t = 0.88 * _logi(wl, 408, 10) * (1 - _logi(wl, 508, 14))
        t += 0.05 * _logi(wl, 560, 20) * (1 - _logi(wl, 640, 20))   # small green-side leak
    elif c == "G":
        t = 0.86 * _logi(wl, 482, 12) * (1 - _logi(wl, 596, 14))
        t += 0.04 * _logi(wl, 420, 15) * (1 - _logi(wl, 470, 12))   # small blue-side leak
    elif c == "R":
        t = 0.92 * _logi(wl, 598, 13)
        t += 0.03 * _logi(wl, 480, 20) * (1 - _logi(wl, 560, 20))
    else:
        raise ValueError(f"unknown CFA color {color!r}")
    if nir_leak and c in "RGB":
        # organic dyes are essentially transparent beyond ~700 nm
        t = np.maximum(t, 0.90 * _logi(wl, 715, 22))
    return np.clip(t, 0.0, 1.0)


def stacked_cfa_transmittance(wl_nm, layers=("R", "B"), nir_leak: bool = True):
    """Transmission through multiple CFA dye layers in series.

    Each layer curve is the transmission of one nominal-thickness filter, so
    an R+B visible-cut IR cell is represented by ``T_R * T_B``.  Interface
    reflection and coherent thin-film interference are outside this scalar CFA
    model, consistent with :func:`cfa_transmittance`.
    """
    wl = np.asarray(wl_nm, float)
    out = np.ones_like(wl)
    for color in layers:
        out *= cfa_transmittance(wl, color, nir_leak=nir_leak)
    return np.clip(out, 0.0, 1.0)


def ircf_transmittance(wl_nm, cut_nm: float = 650.0, width_nm: float = 18.0):
    """Absorptive/interference IR-cut filter in front of the sensor."""
    wl = np.asarray(wl_nm, float)
    return 0.97 * (1 - _logi(wl, cut_nm, width_nm)) * _logi(wl, 395, 8)


# --------------------------------------------------------------------------
# Dielectrics of the stack (weakly dispersive -> constants are fine)
# --------------------------------------------------------------------------
N_MICROLENS = 1.60      # photoresist / styrene microlens
N_PLANAR = 1.46         # planarization / SiO2
N_CFA = 1.55            # dye-in-resin color filter
N_ARC = 2.00            # SiN anti-reflection coating on the Si backside


def arc_transmittance(wl_nm, n_top=N_PLANAR, d_arc_um=0.0688, n_arc=N_ARC,
                      theta_deg=0.0):
    """Power transmittance top -> ARC -> Si through a single ARC layer (TMM).

    `theta_deg` is the propagation angle inside the top medium; s and p are
    averaged, which is the right thing for unpolarised light.  Default ARC
    thickness is a quarter wave at 550 nm for n=2.0.
    """
    wl = np.atleast_1d(np.asarray(wl_nm, float))
    ns = si_index_complex(wl)
    k0 = 2 * np.pi / (wl * 1e-3)
    sin_t = n_top * np.sin(np.deg2rad(theta_deg))          # conserved n*sin(theta)
    c_top = np.sqrt(1 - (sin_t / n_top) ** 2 + 0j)
    c_arc = np.sqrt(1 - (sin_t / n_arc) ** 2 + 0j)
    c_sub = np.sqrt(1 - (sin_t / ns) ** 2 + 0j)
    d = n_arc * k0 * d_arc_um * c_arc
    cosd, sind = np.cos(d), np.sin(d)
    out = 0.0
    for pol in ("s", "p"):
        if pol == "s":
            e_top, e_arc, e_sub = n_top * c_top, n_arc * c_arc, ns * c_sub
        else:
            e_top, e_arc, e_sub = n_top / c_top, n_arc / c_arc, ns / c_sub
        B = cosd + 1j * sind / e_arc * e_sub
        C = 1j * e_arc * sind + cosd * e_sub
        out = out + 4 * np.real(e_top) * np.real(e_sub) / np.abs(e_top * B + C) ** 2
    t = np.clip(np.real(out) / 2, 0.0, 1.0)
    return t if t.size > 1 else float(t[0])
