"""bxsim - Bayer CMOS image sensor colour-crosstalk simulator (no paid tools)."""
from .stack import PixelStack
from .crosstalk import Simulator, color_mixing_matrix, ccm_noise_gain, planck
from . import materials, optics, diffusion

__all__ = ["PixelStack", "Simulator", "color_mixing_matrix", "ccm_noise_gain",
           "planck", "materials", "optics", "diffusion"]
__version__ = "0.1.0"
