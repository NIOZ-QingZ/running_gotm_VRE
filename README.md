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
