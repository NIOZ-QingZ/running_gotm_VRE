# Model code fixes (BFM 2016 / GOTM / GETM)

Log of bugs found in the model code: what is wrong, how it was found, what it
does to the results and how it was fixed. One entry per bug, newest at the top
of the table. Scientific changes (new parameters, new processes) are not bugs;
they stay in the patch list in [README.md](README.md#local-model-changes).

**Status values:** `open` (found, not fixed) · `fixed-patch` (fix in a patch
file, applied at image build) · `fixed-source` (fixed in the BFM repository) ·
`no-fix` (checked, not a bug or left on purpose).

## Overview

| ID | Status | File | Short description | Affects GETM runs | Found |
| --- | --- | --- | --- | --- | --- |
| FIX-001 | open | `src/BFM/Ben/FilterFeeder.F90` | microzooplankton food summed over boxes instead of groups (`sum(ZI_Fc,1)`) | yes | 2026-11-23, code review (colleague) |

## How to add an entry

1. Add a row to the table above and a section below (copy the template).
2. Fix the source in `Container_dependency/Model_source_codes/bfm_2016`
   (branch `bfm2016_production_20250827`), and keep the fix in its own patch:
   `git -C Container_dependency/Model_source_codes/bfm_2016 diff -- <files> > Container_dependency/patches/fix_<ID>_<name>.patch`
   (one patch per fix, so fixes can be applied or reverted one by one, and
   are kept apart from scientific changes).
3. Add the patch name to the patch loop in the [Dockerfile](Dockerfile)
   (`for p in ...`), so an image built from a fresh GitHub clone also gets it.
4. Rebuild the debug image, rerun the check that found the bug, and note the
   result under *Verification*.
5. Commit the patch, the Dockerfile and this file together, with the ID in the
   commit message (e.g. `FIX-001: sum ZI_Fc over groups`). `git log --grep FIX-001`
   then lists everything that belongs to the fix.
6. The GETM source (`GETM_ERSEM_SETUPS/Container_dependency/...` and
   `BFM_SOURCES/bfm_2016`) has its own copies of the BFM files: note under
   *GETM copies* whether they are fixed as well.

### Template

```markdown
## FIX-00N: <short title>

- **Status:** open | fixed-patch | fixed-source | no-fix
- **File / lines:** `src/BFM/...F90:NNN`
- **Found:** YYYY-MM-DD, <debug build / code review / budget check / ...>
- **Problem:** what the code does and what it should do.
- **Cause:** why (e.g. leftover from a change of array layout).
- **Effect on results:** which variables, how large (estimate or test run).
- **Fix:** the code change (patch file name).
- **Verification:** the run or check that shows the fix works.
- **GETM copies:** fixed / not fixed in the GETM source.
```

## Debug build (how to find bugs)

The image can be built with a GOTM debug build (no optimisation, with runtime
checks); GETM is not affected:

```bash
docker build --build-arg GOTM_BUILD=Debug -t qingzfly/getm-wad-container:debug .
```

`/opt/local/gotm/BUILD_INFO` in the image records the build type, the flags and
the BFM commit; `/opt/home/build/gotm/build.log` keeps the compiler warnings
(`-Wall`).

Run a short OysterGrounds case (1–2 years is enough) and fix whatever stops
the run, one at a time:

```bash
singularity exec --cleanenv --bind $RUN_ROOT getm-wad-container_debug.sif \
  gotm-run --out $RUN_ROOT/og_debug \
           --start "1972-01-01 00:00:00" --stop "1973-12-31 00:00:00"
```

1. `-fcheck=all` (default): out-of-bounds indices, arrays of different shape,
   pointer errors. The run stops with file and line (`-fbacktrace`).
2. When step 1 runs through, add floating-point traps:
   `--build-arg GOTM_DEBUG_FFLAGS="-O0 -g -fbacktrace -fcheck=all -finit-real=snan -Wall -ffpe-trap=invalid,zero,overflow"`.
   Expect some harmless stops in old BFM code; each one needs a decision
   (log it as `no-fix` when it is harmless).
3. Read the warnings in `build.log` once, mainly "may be used uninitialized".
4. Repeat with the scenario switches on (e.g. `--set FilterFeeder.nml:sw_quality=1`,
   `--set FilterFeeder.nml:sw_lim=3`), so new code paths are checked too.

The OysterGrounds case calls BFM with one water column (`NO_BOXES_XY = 1`), as
GETM does, so it checks the BFM code that GETM runs. It does not check GETM's
own code (`src/getm`, transport, restart reading) or processes that do not
happen at a deep North Sea site (drying of tidal flats). For those, run a few
days of GETM built with the same flags.

---

## FIX-001: microzooplankton food summed over boxes instead of groups

- **Status:** open
- **File / lines:** `src/BFM/Ben/FilterFeeder.F90:362` (food) and `:628`
  (uptake limit), in the local copy `Container_dependency/Model_source_codes/bfm_2016`.
- **Found:** 2026-11-23, code review by a colleague; confirmed by reading the
  allocation code.
- **Problem:** `cx_any=sum(ZI_Fc,1)` sums over the first dimension of `ZI_Fc`.
  `ZI_Fc` is `ZI_Fc(box, group)` (Z5 microzooplankton, Z6 heterotrophic
  nanoflagellates), so the sum runs over the boxes, not over the two groups.
  It should be `sum(ZI_Fc,2)`.
- **Cause:** leftover from the change of array layout in `AllocateMem.F90`:
  the old code (`AllocateMem.F90.keep`) had
  `ZI_Fc => D2DIAGNOS(ppZI_Fc(iiZ5):ppZI_Fc(iiZ6),:)` = `(group, box)`; the
  current code has `ZI_Fc => D2DIAGNOS(:,ppZI_Fc(iiZ5):ppZI_Fc(iiZ6))` =
  `(box, group)`. The uptake loop was changed to `ZI_Fc(:,i)`, these two sums
  were not.
- **Effect on results:** GOTM and GETM call BFM with one column
  (`NO_BOXES_XY = 1`), so `sum(ZI_Fc,1)` gives two values `[Z5, Z6]` that are
  assigned to `cx_any(1)`. This is invalid Fortran; without bounds checks
  `cx_any` in practice gets Z5 only. Then:
  - Z6 is missing from the microzooplankton food `food_ZI` and from the total
    food `food` (affects food saturation `efsatY3` and the food used for spawning);
  - the uptake limits against the bottom layer use Z5 only;
  - Z6 is still eaten in the uptake loop (`ZI_Fc(:,i)*suf*choice`), at a rate set
    by Z5.
  Expected to be small: micro + mesozooplankton gave about 3–5 % of the
  suspension-feeder ingestion in the Wadden Sea spin-up runs (2015).
- **Fix (proposed):** in both lines, `sum(ZI_Fc,1)` → `sum(ZI_Fc,2)`.
- **Verification (to do):** the debug build should stop at line 362 with
  "Array bound mismatch for dimension 1 of array 'cx_any' (1/2)" before the
  fix and run through after it; `foodZIY3` should increase by about the Z6
  concentration near the bed, `ruZIY3c` should change little.
- **GETM copies:** not fixed. Same two lines in
  `BFM_SOURCES/bfm_2016/src/BFM/Ben/FilterFeeder.F90` (364, 638) and
  `GETM_ERSEM_SETUPS/Container_dependency/SuspensionFeeders_update/FilterFeeder.F90`
  (364, 638).
