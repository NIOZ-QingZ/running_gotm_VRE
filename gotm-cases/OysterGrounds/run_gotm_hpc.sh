#!/bin/bash
#SBATCH --job-name=gotm_OG
#SBATCH --partition=normal
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --time=0-18:00:00
#SBATCH --mem=2G
#SBATCH --output=gotm_OG_%j.out

# run script for GOTM-BFM (OysterGrounds) on the HPC
# submit from the case directory:  sbatch run_gotm_hpc.sh
# based on run_gotm_laplace / run_gotm_batch_qing

set -u

echo "*****************************"
echo "Starting GOTM-BFM run on $(hostname), job ${SLURM_JOB_ID:-none}"

# load modules needed by the native gotm build (netcdf etc.), if any
# module load ...

# gotm executable: native build by default, can be overridden from outside
GOTM_EXE=${GOTM_EXE:-/export/lv9/user/qzhan/local/gotm/bin/gotm}
tidecalc=${TIDECALC:-/export/lv9/user/qzhan/home/FORTRAN_SOURCES/calc_GOTM_tidalforcing.x}

run_dir=${SLURM_SUBMIT_DIR:-$(pwd)}
out_dir=${OUT_DIR:-/export/lv9/user/qzhan/model_output/active_runs/gotm}
cd "$run_dir" || exit 1

#----------------------------------
# !!!! make sure start and stop time match those set in gotmrun.nml !!!
export start="1972-01-01 00:00:00"
export stop="2008-12-31 00:00:00"

export out_fn="OysterGrounds"  # run ID, must match title in gotmrun.nml
export site_id='og'  # should be in lower case
#----------------------------------

filename=$out_fn.nc
echo 'Run set from ' $start ' to ' $stop
echo 'gotm executable: ' $GOTM_EXE
if [ ! -x "$GOTM_EXE" ] ; then
  echo " gotm executable not found: $GOTM_EXE"
  exit 1
fi

t1=$(date +%s)

# copy nml files to output directory
echo 'copying input files to ' $out_dir/$out_fn
mkdir -p $out_dir/$out_fn/plots
cp bio_bfm.nml $out_dir/$out_fn/
tar -zcf $out_dir/$out_fn/nml.tgz *.nml

# create tidal input series --> depends on start and end time
# if the tidal program is not available, the existing pressure.dat is used
if [ -x "$tidecalc" ] ; then
  echo 'Starting tidal calculation'
  "$tidecalc" > tidal.out 2>&1
else
  echo "Tidal program not found ($tidecalc), using existing pressure.dat"
  head -1 pressure.dat
  tail -1 pressure.dat
fi

# actual run
echo 'Starting GOTM-BFM'
rm -f log.out
"$GOTM_EXE" --read_nml > log.out 2>&1
status=$?
OKready=$(tail -20 log.out | grep "Simulated time/CPU time")

if [ -n "$OKready" ] ; then
  echo " GOTM-BFM made it ..."
  t2=$(date +%s)
  echo "wall clock time: $((t2-t1)) secs"
  echo "wall clock time: $((t2-t1)) secs" >> log.out

  echo 'copying output files to ' $out_dir/$out_fn
  mv $filename $out_dir/$out_fn/
  cp log.out pressure.dat $out_dir/$out_fn/
  [ -f zeta.dat ] && cp zeta.dat $out_dir/$out_fn/
  [ -f tidal.out ] && cp tidal.out $out_dir/$out_fn/
  echo "GOTM-BFM run finished!"
else
  echo " GOTM-BFM run FAILED (exit code $status), last lines of log.out:"
  tail -20 log.out
  exit 1
fi
echo "*****************************"
