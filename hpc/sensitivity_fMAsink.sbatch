#!/bin/bash
#SBATCH --job-name=fMAsink
#SBATCH --partition=normal
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --mem=2G
#SBATCH --time=0-08:00:00
#SBATCH --array=1-5
#SBATCH --output=fMAsink_%A_%a.out

# Sensitivity of the suspension feeders (Y3) to the macroaggregate sinking
# rate: one array task per line of fMAsink_values.txt, each one GOTM-BFM run
# of the OysterGrounds case inside the Singularity image.
#
# Submit from this folder (the --array range must match the number of values):
#   sbatch sensitivity_fMAsink.sbatch
#   sbatch --array=1-$(wc -l < fMAsink_values.txt) sensitivity_fMAsink.sbatch
#
# Settings can be overridden from outside, e.g.
#   SIF=~/Singularity_containers/other.sif STOP="1980-01-01 00:00:00" sbatch ...

set -eu

SIF=${SIF:-$HOME/Singularity_containers/getm-wad-container_fMAsink.sif}
VALUES=${VALUES:-$SLURM_SUBMIT_DIR/fMAsink_values.txt}
OUT_ROOT=${OUT_ROOT:-/export/lv9/user/$USER/model_output/sensitivity/fMAsink}
# OysterGrounds case baked into the image; set CASE to a folder on laplace to
# run your own copy instead (it is bound into the container below).
CASE=${CASE:-/opt/cases/OysterGrounds}
START=${START:-1972-01-01 00:00:00}
STOP=${STOP:-2008-12-31 00:00:00}

value=$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$VALUES" | tr -d '[:space:]')
if [ -z "$value" ]; then
  echo "no value on line $SLURM_ARRAY_TASK_ID of $VALUES"
  exit 1
fi
run_dir=$OUT_ROOT/fMAsink_$value

module load singularity 2>/dev/null || true
mkdir -p "$OUT_ROOT"

binds="$OUT_ROOT"
case "$CASE" in
  /opt/*) ;;
  *) binds="$binds,$CASE" ;;
esac

echo "task $SLURM_ARRAY_TASK_ID on $(hostname): p_fMAsink=$value -> $run_dir"
singularity exec --cleanenv --bind "$binds" "$SIF" \
  gotm-run --case "$CASE" --out "$run_dir" \
           --set "PelGlobal.nml:p_fMAsink=$value" \
           --start "$START" --stop "$STOP"
