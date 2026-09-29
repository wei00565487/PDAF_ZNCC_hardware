#!/usr/bin/env python3
"""Create a routing-only SRAM LEF abstraction for the Nangate45 demo flow.

This does not generate SRAM circuitry or GDS.  It preserves the macro size,
pin names and pin directions, but enlarges/snap-centers abstract signal pins
so OpenROAD can find legal access points on the Nangate45 routing grid.
"""
from pathlib import Path
import re
import sys

src, dst = map(Path, sys.argv[1:3])
text = src.read_text()

pin_re = re.compile(r"(PIN\s+[^\n]+\n.*?\n\s*END\s+[^\n]+)", re.S)
rect_re = re.compile(r"(RECT\s+)([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)\s+([-+0-9.]+)(\s*;)")

def rewrite_pin(m):
    block = m.group(1)
    # Keep the original metal3 pin layer.  The source abstraction has a
    # metal3 OBS with openings around these pins; moving the pins to metal1
    # would put them underneath the full-macro metal1 obstruction.
    # This remains a routeability proxy; the real SRAM compiler must supply
    # matching pin layers and GDS shapes.
    def rewrite_rect(r):
        x1, y1, x2, y2 = map(float, r.group(2, 3, 4, 5))
        # Keep the original pin center and stay inside the existing metal3
        # obstruction opening (0.135um is the source pin width/height).
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        nx1, nx2 = cx - 0.14, cx + 0.14
        ny1, ny2 = cy - 0.14, cy + 0.14
        # FreePDK45/Nangate45 uses a 0.005um manufacturing grid.
        # Snap every LEF coordinate so placed macro origins cannot produce
        # half-grid pin shapes in detailed routing.
        snap = lambda v: round(v / 0.005) * 0.005
        nx1, nx2 = snap(nx1), snap(nx2)
        ny1, ny2 = snap(ny1), snap(ny2)
        return f"{r.group(1)}{nx1:.4f} {ny1:.4f} {nx2:.4f} {ny2:.4f}{r.group(6)}"
    return rect_re.sub(rewrite_rect, block)

dst.parent.mkdir(parents=True, exist_ok=True)
text = pin_re.sub(rewrite_pin, text)

# The source macro has full metal1/metal2 obstruction and a detailed metal3
# obstruction pattern.  For a P&R-only proxy, keep m1/m2 blockage but remove
# the m3 obstruction so enlarged m3 signal ports have legal access points.
if "   OBS\n" in text:
    head, obs = text.split("   OBS\n", 1)
    obs = re.sub(r"\s+LAYER\s+metal3\s*;.*?(?=\s+LAYER\s+metal4\s*;)", "", obs, flags=re.S)
    text = head + "   OBS\n" + obs

# Populate the empty power ports from the source abstraction.  These are
# proxy shapes only; the real SRAM IP must provide actual VDD/VSS geometry.
size_m = re.search(r"SIZE\s+([0-9.]+)\s+BY\s+([0-9.]+)\s*;", text)
if size_m:
    w, h = map(float, size_m.groups())
    power_re = re.compile(r"(PIN\s+(vdd|gnd)\s+.*?PORT\s*)END(\s*END\s+\2)", re.S)
    def power_pin(m):
        name = m.group(2)
        y1, y2 = (0.14, 0.42) if name == "vdd" else (h - 0.42, h - 0.14)
        port = f"LAYER metal4 ;\n         RECT  0.1400 {y1:.4f} {w - 0.1400:.4f} {y2:.4f} ;\n      "
        return m.group(1) + port + "END" + m.group(3)
    text = power_re.sub(power_pin, text)

dst.write_text(text)
print(dst)
