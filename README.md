# GOTM-BFM / GETM container

Docker image with GOTM-BFM (1D) and GETM (3D) compiled as on the NIOZ HPC
(Ubuntu 18.04, GCC 6, netCDF 4.6). The same image is used

1. on **laplace** as a Singularity image, for sensitivity runs, and
2. in the **NaaVRE** virtual lab, as a workflow component.

Both use the same command, `gotm-run`, so a run on laplace and a run in NaaVRE
are described by the same arguments.

## What is in the image

| Path | Content |
| --- | --- |
| `/opt/local/gotm/bin/gotm` | GOTM-BFM executable |
| `/opt/local/getm/gfortran/bin/getm` | GETM executable (dws_200m, 32x32) |
| `/opt/cases/OysterGrounds` | OysterGrounds GOTM case (forcing and tides 1972–2008) |
| `/usr/local/bin/gotm-run` | run tool ([Container_dependency/gotm_run.py](Container_dependency/gotm_run.py)) |
| `/opt/home/patches` | local changes to the model sources ([Container_dependency/patches](Container_dependency/patches)) |

### Local model changes

- [bfm_p_fMAsink.patch](Container_dependency/patches/bfm_p_fMAsink.patch):
  new parameter `p_fMAsink` in `/PelGlobal_parameters/` (`PelGlobal.nml`)
  that scales the macroaggregate sinking rate in `PelGlobal.F90`. The default
  is 1.0, which gives the same results as the unpatched model, so existing
  `PelGlobal.nml` files keep working.
- [bfm_silt_fluff.patch](Container_dependency/patches/bfm_silt_fluff.patch):
  silt `method=5` in `Silt.nml`, after Baretta & Ruardij (1988, Chap. 5.3).
  Sedimentation and resuspension follow their eq. 5.3–5.5 (wind-dependent
  `pDOWN`, `seddep`, `resdep`), with a new benthic state variable `Q8x`
  (fluff layer on the bed, mg/m²) between the water and the bed. Silt moves
  between `Q8x` and the bottom water layer of `R9x` only, so the total is
  conserved. New parameters in `Silt_parameters`: `p_pDOWN0`, `p_W50`,
  `p_minwind`, `p_seddep`, `p_resdep`, `p_rtid` (defaults: Ems-Dollard values);
  initial value `Q8x0` in `bfm_ben_init_nml` (default 10 g/m²). The default
  `method=4` gives the same results as before. Example:
  `gotm-run --out RUN --set Silt.nml:Silt_parameters:method=5`.

The patches are applied during the build; a patch is skipped when its changes
are already in a local source copy (`Container_dependency/Model_source_codes`).
To update a patch after changing the BFM source there:
`git -C Container_dependency/Model_source_codes/bfm_2016 diff > Container_dependency/patches/<name>.patch`.

## `gotm-run`

```bash
gotm-run --out RUN_DIR [--case CASE_DIR] [--set FILE:[GROUP:]NAME=VALUE ...] \
         [--start "YYYY-MM-DD hh:mm:ss"] [--stop "YYYY-MM-DD hh:mm:ss"]
```

1. copies the case (default `/opt/cases/OysterGrounds`) to `RUN_DIR`,
2. writes the model output into `RUN_DIR` and sets the start/stop time in `gotmrun.nml`,
3. applies each `--set`, e.g. `--set PelGlobal.nml:p_fMAsink=2.0`
   (the name is added to the namelist if the file does not have it yet),
4. runs `gotm --read_nml`.

Results in `RUN_DIR`:

- `OG.nc`: BFM output, e.g. `Y3c` (suspension feeders), `jnetY3c`, `jRIY3c`, `jZIY3c`
- `OysterGrounds.nc`: physics output
- `log.out`: model log. The namelist echo shows the values used (`P_FMASINK= ...`).
- `run_info.json`: arguments, wall time and `status` (`finished` / `failed`)

The exit code is 0 only when the run finished. Runtime is about 1 s per
simulated day, so about 4 h for 1972–2008.

## 1. Build and push the image (on your PC)

The model sources come from private GitHub repositories, so the build needs your
SSH key (see the comments at the end of the [Dockerfile](Dockerfile)):

```powershell
$env:DOCKER_BUILDKIT=1; docker build --ssh default -t getm-wad-container:fMAsink .
```

Quick test (10 days):

```powershell
docker run --rm getm-wad-container:fMAsink gotm-run --out /tmp/test --stop "1972-01-11 00:00:00"
```

Push to Docker Hub:

```powershell
docker login
docker tag getm-wad-container:fMAsink qingzfly/getm-wad-container:fMAsink
docker push qingzfly/getm-wad-container:fMAsink
```

> **The image contains the private model source code** (`/opt/home/BFM_SOURCES`,
> `gotm-git`, `getm-git`). `qingzfly/getm-wad-container` is a public Docker
> Hub repository, so pushing there makes that code readable to anyone. Make the
> repository private (Docker Hub → repository → Settings → Visibility), or get
> agreement from the code owners first. With a private repository, laplace and
> NaaVRE need Docker Hub credentials to pull it (see below).

## 2. Sensitivity runs on laplace

Pull the image once:

```bash
module load singularity
singularity pull ~/Singularity_containers/getm-wad-container_fMAsink.sif \
    docker://qingzfly/getm-wad-container:fMAsink
# private repository: add --docker-login
```

Copy the [hpc](hpc) folder to laplace, then edit
[fMAsink_values.txt](hpc/fMAsink_values.txt) (one value per line) and submit
one array task per value:

```bash
cd hpc
sbatch --array=1-$(wc -l < fMAsink_values.txt) sensitivity_fMAsink.sbatch
```

Each task runs
`singularity exec ... gotm-run --out $OUT_ROOT/fMAsink_<value> --set PelGlobal.nml:p_fMAsink=<value>`.
Settings can be changed through environment variables when you submit:

| Variable | Default |
| --- | --- |
| `SIF` | `~/Singularity_containers/getm-wad-container_fMAsink.sif` |
| `OUT_ROOT` | `/export/lv9/user/$USER/model_output/sensitivity/fMAsink` |
| `CASE` | `/opt/cases/OysterGrounds` (the copy in the image) |
| `START`, `STOP` | `1972-01-01 00:00:00`, `2008-12-31 00:00:00` |

For example, a shorter test sweep: `STOP="1975-01-01 00:00:00" sbatch --array=1-5 sensitivity_fMAsink.sbatch`.

Check the results with `grep status $OUT_ROOT/*/run_info.json`, then compare
`Y3c` in `$OUT_ROOT/fMAsink_*/OG.nc`.

### One-year sweep and figure (p_fMAsink 1–6)

[fMAsink_values.txt](hpc/fMAsink_values.txt) holds 1, 2, …, 6. Run the year
1972 (about 6 min per run):

```bash
cd hpc
START="1972-01-01 00:00:00" STOP="1973-01-01 00:00:00" sbatch --array=1-6 --time=0-01:00:00 sensitivity_fMAsink.sbatch
```

When all six tasks have finished, make the figure with
[plot_fMAsink.py](hpc/plot_fMAsink.py). It runs inside the image, so nothing
needs to be installed on laplace:

```bash
OUT_ROOT=/export/lv9/user/$USER/model_output/sensitivity/fMAsink
SIF=~/Singularity_containers/getm-wad-container_fMAsink.sif
singularity exec --cleanenv --bind $OUT_ROOT $SIF python3 plot_fMAsink.py $OUT_ROOT --year 1972
```

This writes `$OUT_ROOT/fMAsink_Y3c_1972.png` and a `.csv` with the numbers:
(a) the annual mean suspension-feeder biomass `Y3c` against p_fMAsink,
labelled with the % change from p_fMAsink = 1, and (b) the daily `Y3c` through
the year for each value. `--var` selects another BFM variable, e.g.
`--var jnetY3c` for net production.

The run starts from the initial values in `bio_bfm.nml` (`Y3c0 = 800`), so a
single year mostly shows the first response. For a response less affected by
the start state, run more years (e.g. `STOP="1976-01-01 00:00:00"`) and plot
a later year (`--year 1975`).

## 3. NaaVRE workflow component

The workflow component wraps one `gotm-run` call. Specification for the
NaaVRE developer:

- **Image:** `qingzfly/getm-wad-container:fMAsink`
- **Command:** `gotm-run --out <run_dir> --set PelGlobal.nml:p_fMAsink=<p_fMAsink> --start <start> --stop <stop>`
- **Inputs**

  | Name | Type | Example |
  | --- | --- | --- |
  | `p_fMAsink` | float | `2.0` |
  | `start` | string | `1972-01-01 00:00:00` |
  | `stop` | string | `2008-12-31 00:00:00` |
  | `case` (optional) | directory | default `/opt/cases/OysterGrounds` in the image |

- **Outputs:** `<run_dir>/OG.nc` (BFM, incl. `Y3c`), `<run_dir>/OysterGrounds.nc`,
  `<run_dir>/log.out`, `<run_dir>/run_info.json`. A non-zero exit code means the run failed.
- **Sensitivity sweep:** the workflow gives a list of `p_fMAsink` values to
  this component (one run per value, in parallel), followed by a step that
  compares `Y3c` across runs.

Other namelist parameters of the case can be varied the same way with more
`--set FILE:NAME=VALUE` arguments.
