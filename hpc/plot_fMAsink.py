#!/usr/bin/env python3
"""Plot the p_fMAsink sensitivity of the suspension feeders (Y3).

Reads OG.nc from every run directory made by sensitivity_fMAsink.sbatch
(<OUT_ROOT>/fMAsink_<value>), averages the variable over one year and plots

  (a) the annual mean against p_fMAsink, with the change relative to
      p_fMAsink = 1 (the unchanged model), and
  (b) the daily values through that year, one line per p_fMAsink.

The numbers are also written to a CSV next to the figure. Runs inside the
image, e.g. on laplace:

  singularity exec --bind $OUT_ROOT $SIF python3 plot_fMAsink.py $OUT_ROOT --year 1972
"""
import argparse
import csv
import datetime
import glob
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import netCDF4
import numpy as np


def fmasink_of(run_dir):
    """p_fMAsink of a run: from run_info.json, else from the folder name."""
    info = os.path.join(run_dir, "run_info.json")
    if os.path.isfile(info):
        with open(info) as f:
            for s in json.load(f).get("set", []):
                m = re.search(r"p_fMAsink=([-+0-9.eE]+)", s)
                if m:
                    return float(m.group(1))
            return 1.0  # run without --set: model default
    m = re.search(r"fMAsink_([-+0-9.eE]+)$", run_dir.rstrip("/"))
    return float(m.group(1)) if m else None


def read_year(path, var, year):
    """Dates and values of `var` (first grid point) within `year`."""
    with netCDF4.Dataset(path) as nc:
        t = nc.variables["time"]
        # num2date may return cftime dates, which matplotlib cannot plot:
        # convert them to standard Python datetimes
        dates = [datetime.datetime(d.year, d.month, d.day, d.hour, d.minute, d.second)
                 for d in netCDF4.num2date(t[:], t.units)]
        values = np.ma.filled(nc.variables[var][:].reshape(len(dates), -1)[:, 0], np.nan)
        units = getattr(nc.variables[var], "units", "")
        long_name = getattr(nc.variables[var], "long_name", var)
    keep = np.array([d.year == year for d in dates])
    return [d for d, k in zip(dates, keep) if k], values[keep], units, long_name


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_root", help="folder with the fMAsink_<value> run directories")
    p.add_argument("--year", type=int, required=True, help="year to average over")
    p.add_argument("--var", default="Y3c", help="BFM variable in OG.nc (default: %(default)s)")
    p.add_argument("--fig", help="output figure (default: <out_root>/fMAsink_<var>_<year>.png)")
    args = p.parse_args()

    runs = []
    for run_dir in sorted(glob.glob(os.path.join(args.out_root, "fMAsink_*"))):
        nc_path = os.path.join(run_dir, "OG.nc")
        f = fmasink_of(run_dir)
        if f is None or not os.path.isfile(nc_path):
            print("skipping %s (no OG.nc or p_fMAsink)" % run_dir)
            continue
        dates, values, units, long_name = read_year(nc_path, args.var, args.year)
        if len(values) == 0:
            print("skipping %s (no output in %d)" % (run_dir, args.year))
            continue
        runs.append((f, dates, values))
    if not runs:
        sys.exit("ERROR: no usable runs in %s for %d" % (args.out_root, args.year))
    runs.sort(key=lambda r: r[0])

    fs = np.array([r[0] for r in runs])
    means = np.array([np.nanmean(r[2]) for r in runs])
    ref = means[np.argmin(abs(fs - 1.0))] if np.any(np.isclose(fs, 1.0)) else means[0]
    change = 100.0 * (means - ref) / ref

    base = args.fig or os.path.join(args.out_root,
                                    "fMAsink_%s_%d.png" % (args.var, args.year))
    with open(os.path.splitext(base)[0] + ".csv", "w") as f:
        w = csv.writer(f)
        w.writerow(["p_fMAsink", "mean_%s_%s" % (args.var, units), "change_percent", "n_days"])
        for (fv, _, v), m, c in zip(runs, means, change):
            w.writerow([fv, "%.3f" % m, "%.2f" % c, int(np.sum(~np.isnan(v)))])
            print("p_fMAsink=%-5g mean %s = %9.2f %s (%+6.2f %%)" % (fv, args.var, m, units, c))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    colors = plt.cm.viridis(np.linspace(0, 0.9, len(runs)))

    ax1.plot(fs, means, "-", color="0.6", zorder=1)
    ax1.scatter(fs, means, c=colors, s=50, zorder=2)
    for fv, m, c in zip(fs, means, change):
        ax1.annotate("%+.1f%%" % c, (fv, m), textcoords="offset points",
                     xytext=(0, 8), ha="center", fontsize=9)
    ax1.set_xlabel("p_fMAsink (macroaggregate sinking scaling factor)")
    ax1.set_ylabel("annual mean %s [%s]" % (args.var, units))
    ax1.set_title("(a) %s, mean over %d" % (long_name, args.year), fontsize=10)
    ax1.set_xticks(fs)
    ax1.margins(y=0.12)  # room for the % labels

    for (fv, dates, values), col in zip(runs, colors):
        ax2.plot(dates, values, color=col, label="%g" % fv)
    ax2.set_ylabel("%s [%s]" % (args.var, units))
    ax2.set_title("(b) daily values in %d" % args.year, fontsize=10)
    ax2.legend(title="p_fMAsink", fontsize=8, frameon=False)
    fig.autofmt_xdate()

    fig.tight_layout()
    fig.savefig(base, dpi=150)
    print("figure: %s" % base)


if __name__ == "__main__":
    main()
