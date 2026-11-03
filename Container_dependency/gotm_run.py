#!/usr/bin/env python3
"""Run one GOTM-BFM simulation in a fresh copy of a case directory.

Installed in the image as `gotm-run`. The same command is used on the HPC
(singularity exec) and as the NaaVRE workflow component, so a run is fully
described by its command line:

  gotm-run --out /path/run_fMAsink_2.0 \
           --set PelGlobal.nml:p_fMAsink=2.0 \
           --start "1972-01-01 00:00:00" --stop "1973-01-01 00:00:00"

Steps: copy the case into --out, point the output of gotmrun.nml to that
directory, apply the namelist changes, run `gotm --read_nml`, and write
run_info.json with the settings and the outcome. Exit code 0 means the run
finished ("Simulated time/CPU time" in log.out).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

DEFAULT_CASE = "/opt/cases/OysterGrounds"
DEFAULT_GOTM = "/opt/local/gotm/bin/gotm"


def set_namelist_value(path, name, value, group=None):
    """Set `name = value` in a Fortran namelist file.

    Replaces the existing assignment (inside `group` when given); if the name
    is not assigned yet, it is added at the end of `group`, or of the first
    group in the file. Comment lines (starting with !) are left alone.
    """
    with open(path) as f:
        lines = f.readlines()

    current = None      # namelist group we are in, None outside a group
    target_end = None   # index of the closing "/" of the group to append to
    assign = re.compile(r"^(\s*)" + re.escape(name) + r"\s*=", re.IGNORECASE)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("!"):
            continue
        m = re.match(r"&(\w+)", stripped)
        if m:
            current = m.group(1)
            continue
        if current is None:
            continue
        in_target = group is None or current.lower() == group.lower()
        if stripped.startswith("/"):
            if in_target and target_end is None:
                target_end = i
            current = None
            continue
        if in_target and assign.match(line):
            indent = assign.match(line).group(1)
            lines[i] = "%s%s = %s,\n" % (indent, name, value)
            break
    else:
        if target_end is None:
            sys.exit("ERROR: no namelist group %s in %s" % (group or "", path))
        lines.insert(target_end, "   %s = %s,\n" % (name, value))

    with open(path, "w") as f:
        f.writelines(lines)


def parse_set(spec):
    """FILE:[GROUP:]NAME=VALUE -> (file, group, name, value)."""
    try:
        target, value = spec.split("=", 1)
        parts = target.split(":")
        if len(parts) == 2:
            return parts[0], None, parts[1], value
        if len(parts) == 3:
            return parts[0], parts[1], parts[2], value
    except ValueError:
        pass
    raise argparse.ArgumentTypeError(
        "expected FILE:NAME=VALUE or FILE:GROUP:NAME=VALUE, got %r" % spec)


def quoted(text):
    return "'%s'" % text


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--case", default=DEFAULT_CASE,
                   help="case directory to copy (default: %(default)s)")
    p.add_argument("--out", required=True,
                   help="run directory to create; must not exist or be empty")
    p.add_argument("--set", dest="sets", action="append", default=[], type=parse_set,
                   metavar="FILE:[GROUP:]NAME=VALUE",
                   help="namelist change, e.g. PelGlobal.nml:p_fMAsink=2.0 (repeatable)")
    p.add_argument("--start", help='start time, e.g. "1972-01-01 00:00:00"')
    p.add_argument("--stop", help='stop time, e.g. "2008-12-31 00:00:00"')
    p.add_argument("--gotm", default=os.environ.get("GOTM_EXE", DEFAULT_GOTM),
                   help="gotm executable (default: %(default)s)")
    args = p.parse_args()

    case = os.path.abspath(args.case)
    out = os.path.abspath(args.out)
    if not os.path.isfile(os.path.join(case, "gotmrun.nml")):
        sys.exit("ERROR: %s is not a GOTM case (no gotmrun.nml)" % case)
    if os.path.exists(out) and os.listdir(out):
        sys.exit("ERROR: run directory %s is not empty" % out)

    # 1. fresh copy of the case, without results of earlier runs
    if os.path.exists(out):
        os.rmdir(out)
    shutil.copytree(case, out, ignore=shutil.ignore_patterns(
        "log.out", "nohup.out", "slurm-*.out", "run_info.json"))

    # 2. write output into the run directory and set the period
    gotmrun = os.path.join(out, "gotmrun.nml")
    set_namelist_value(gotmrun, "out_dir", quoted("."), "output")
    if args.start:
        set_namelist_value(gotmrun, "start", quoted(args.start), "time")
    if args.stop:
        set_namelist_value(gotmrun, "stop", quoted(args.stop), "time")

    # 3. parameter changes
    for fname, group, name, value in args.sets:
        path = os.path.join(out, fname)
        if not os.path.isfile(path):
            sys.exit("ERROR: %s not found in case" % fname)
        set_namelist_value(path, name, value, group)
        print("set %s %s = %s" % (fname, name, value))

    # 4. run
    info = {
        "case": case,
        "out": out,
        "set": ["%s:%s%s=%s" % (f, (g + ":") if g else "", n, v)
                for f, g, n, v in args.sets],
        "start": args.start,
        "stop": args.stop,
        "gotm": args.gotm,
    }
    print("running %s in %s" % (args.gotm, out))
    t0 = time.time()
    with open(os.path.join(out, "log.out"), "w") as log:
        rc = subprocess.call([args.gotm, "--read_nml"], cwd=out,
                             stdout=log, stderr=subprocess.STDOUT)
    info["wall_seconds"] = round(time.time() - t0, 1)
    info["returncode"] = rc

    with open(os.path.join(out, "log.out")) as log:
        finished = "Simulated time/CPU time" in log.read()[-5000:]
    info["status"] = "finished" if finished else "failed"
    with open(os.path.join(out, "run_info.json"), "w") as f:
        json.dump(info, f, indent=2)

    print("GOTM-BFM run %s after %.0f s (see %s/log.out)"
          % (info["status"], info["wall_seconds"], out))
    sys.exit(0 if finished else 1)


if __name__ == "__main__":
    main()
