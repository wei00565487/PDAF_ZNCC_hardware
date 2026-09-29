#!/usr/bin/env bash
# Matched Meep/BPM convergence benchmark: dielectric stack only, no DTI/grid.
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd -- "$HERE/.." && pwd)"
MEEP_ENV="${MEEP_ENV:-$HOME/.micromamba/envs/meep}"
MPI_NP="${MPI_NP:-8}"

if [[ ! -x "$MEEP_ENV/bin/python" || ! -x "$MEEP_ENV/bin/mpirun" ]]; then
  echo "Meep environment not found at $MEEP_ENV" >&2
  echo "Create it with: micromamba create -f $HERE/environment.yml" >&2
  exit 1
fi

COMMON=(
  --wavelength 550 --cell-pixels 3 --pitch 0.8
  --ml-sag 0.35 --t-ml-to-cfa 0.05 --t-cfa 0.50
  --t-cfa-to-si 0.10 --t-ircf 0 --cfa-grid-width 0
  --si-thickness 3.0 --dti-depth 0 --dti-width 0.10
  --out-dx-nm 50 --out-dz-nm 50 --symmetry 1
)

cd "$ROOT"
export OMP_NUM_THREADS=1
for resolution in 30 45 60; do
  "$MEEP_ENV/bin/mpirun" -np "$MPI_NP" "$MEEP_ENV/bin/python" \
    meep/pixel_fdtd.py "${COMMON[@]}" --resolution "$resolution" \
    --tag "validation_r${resolution}_nodti"
done
