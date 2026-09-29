#!/bin/bash
# Convergence + grid-effect study at the resolution the slab test says we need.
cd /mnt/c/Users/tachi/Documents/bayer-crosstalk-sim/meep
COMMON="--pitch 3.0 --si-thickness 6.0 --dti-depth 6.0 --dti-width 0.20 \
--cell-pixels 3 --ml-sag 0.80 --t-ml-to-cfa 0.10 --t-cfa 0.90 \
--t-cfa-to-si 0.20 --t-ircf 0.30 --wavelength 550 --out-dx-nm 100 --out-dz-nm 100"
for job in "45 0.15 grid_r45" "60 0.15 grid_r60" "60 0.0 nogrid_r60"; do
  set -- $job
  echo "########## resolution $1  cfa-grid $2  tag $3  $(date +%H:%M:%S)"
  mpirun -np 14 python3 pixel_fdtd.py $COMMON --resolution $1 \
         --cfa-grid-width $2 --tag $3 2>&1 \
    | grep -E "cell |own-pixel|total QE|deviation|elapsed|wrote|Error|error"
done
echo "########## ALL DONE $(date +%H:%M:%S)"
