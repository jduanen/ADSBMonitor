#!/usr/bin/env python3
"""
Visualize the 3D tracking volume defined by adsbmon.py's distance constraints.

The three constraints (all optional, each with a min and/or max):
  --groundDistance  horizontal surface distance from receiver (NM)
  --slantDistance   straight-line 3D distance from receiver (NM)
  --altitude        vertical distance from receiver (feet)

Usage examples:
  python viz_volume.py -g 0 50 -a 1000 45000
  python viz_volume.py -g 5 40 -s 5 50 -a 2000 35000
  python viz_volume.py -c config.yaml          # reads constraints from YAML config file

Config file keys: groundDistance, slantDistance, altitude  (each a [min, max] list)
"""

import argparse
import math
import sys

import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 – registers '3d' projection
import yaml


FEET_PER_NM = 6076.115


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parseArgs():
    ap = argparse.ArgumentParser(
        description="Visualize the adsbmon tracking volume in 2-D and 3-D",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument("-a", "--altitude", metavar=("MIN_FT", "MAX_FT"),
                    type=float, nargs=2,
                    help="Altitude constraint: vertical distance from receiver (feet)")
    ap.add_argument("-g", "--groundDistance", metavar=("MIN_NM", "MAX_NM"),
                    type=float, nargs=2,
                    help="Ground distance constraint (NM)")
    ap.add_argument("-s", "--slantDistance", metavar=("MIN_NM", "MAX_NM"),
                    type=float, nargs=2,
                    help="Slant (3-D straight-line) distance constraint (NM)")
    ap.add_argument("-c", "--configFilePath", metavar="PATH",
                    help="Path to adsbmon YAML config file")
    return ap.parse_args()


def loadConfig(path):
    with open(path, encoding="utf-8") as fh:
        docs = list(yaml.load_all(fh, Loader=yaml.Loader))
    return docs[0] if docs else {}


def extractMinmax(value):
    """Return (min, max) from a list/tuple/dict/FilterConstraints-like value."""
    if value is None:
        return None, None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    if hasattr(value, 'min') and hasattr(value, 'max'):
        return value.min, value.max
    if isinstance(value, dict):
        return value.get('min'), value.get('max')
    return None, None


# ---------------------------------------------------------------------------
# Constraint evaluation (vectorised)
# ---------------------------------------------------------------------------

def inVolume(gd, alt_ft, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max):
    """Return boolean array (same shape as gd / alt_ft) indicating valid points.

    Parameters
    ----------
    gd      : array-like, ground distance in NM
    alt_ft  : array-like, altitude relative to receiver in feet
    *_min/max: float or None — constraint bounds
    """
    gd = np.asarray(gd, dtype=float)
    alt_ft = np.asarray(alt_ft, dtype=float)

    ok = np.ones(np.broadcast(gd, alt_ft).shape, dtype=bool)

    if gc_min is not None:
        ok &= gd >= gc_min
    if gc_max is not None:
        ok &= gd <= gc_max

    if alt_min is not None:
        ok &= alt_ft >= alt_min
    if alt_max is not None:
        ok &= alt_ft <= alt_max

    if sc_min is not None or sc_max is not None:
        slant = np.sqrt(gd ** 2 + (alt_ft / FEET_PER_NM) ** 2)
        if sc_min is not None:
            ok &= slant >= sc_min
        if sc_max is not None:
            ok &= slant <= sc_max

    return ok


# ---------------------------------------------------------------------------
# Plot bounds
# ---------------------------------------------------------------------------

def getPlotBounds(gc_min, gc_max, sc_min, sc_max, alt_min, alt_max):
    """Return (gd_max, alt_max_ft) reasonable plot extents."""
    gd_candidates = [v for v in [gc_max, sc_max] if v is not None]
    gd_max = max(gd_candidates) * 1.25 if gd_candidates else 50.0

    # Upper-bound on altitude: prefer the explicit alt_max constraint; fall back
    # to slant-derived ceiling (a slant sphere of radius sc_max can reach at
    # most sc_max * FEET_PER_NM in the vertical direction).  Take the tightest
    # upper bound so the plot is not dominated by a large slant radius when a
    # stricter altitude limit is already in effect.
    alt_upper_candidates = [v for v in [alt_max] if v is not None]
    if sc_max is not None:
        alt_upper_candidates.append(sc_max * FEET_PER_NM)
    if alt_upper_candidates:
        alt_max_ft = min(alt_upper_candidates) * 1.25
    else:
        alt_max_ft = 45_000.0

    return gd_max, alt_max_ft


# ---------------------------------------------------------------------------
# 2-D cross-section
# ---------------------------------------------------------------------------

def plotCrossSection(ax, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max,
                     gd_max, alt_max_ft, N=600):
    """Fill the (ground dist, altitude) cross-section of the tracking volume."""
    gd_vals = np.linspace(0, gd_max, N)
    alt_vals = np.linspace(0, alt_max_ft, N)
    GD, ALT = np.meshgrid(gd_vals, alt_vals)

    mask = inVolume(GD, ALT, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max)

    ax.contourf(GD, ALT / 1000, mask.astype(float),
                levels=[0.5, 1.5], colors=["steelblue"], alpha=0.55)
    ax.contour(GD, ALT / 1000, mask.astype(float),
               levels=[0.5], colors=["navy"], linewidths=1.8)

    # Ground-distance constraint lines (vertical)
    if gc_min is not None:
        ax.axvline(gc_min, color="#2ca02c", ls="--", lw=1.5,
                   label=f"gDist min = {gc_min} NM")
    if gc_max is not None:
        ax.axvline(gc_max, color="#2ca02c", ls="-", lw=1.5,
                   label=f"gDist max = {gc_max} NM")

    # Altitude constraint lines (horizontal)
    if alt_min is not None:
        ax.axhline(alt_min / 1000, color="#ff7f0e", ls="--", lw=1.5,
                   label=f"alt min = {alt_min:,.0f} ft")
    if alt_max is not None:
        ax.axhline(alt_max / 1000, color="#ff7f0e", ls="-", lw=1.5,
                   label=f"alt max = {alt_max:,.0f} ft")

    # Slant constraint arcs (quarter-circle in NM space, scaled to ft on y-axis)
    theta = np.linspace(0, math.pi / 2, 400)
    if sc_min is not None:
        ax.plot(sc_min * np.cos(theta),
                sc_min * np.sin(theta) * FEET_PER_NM / 1000,
                color="#d62728", ls="--", lw=1.5,
                label=f"slant min = {sc_min} NM")
    if sc_max is not None:
        ax.plot(sc_max * np.cos(theta),
                sc_max * np.sin(theta) * FEET_PER_NM / 1000,
                color="#d62728", ls="-", lw=1.5,
                label=f"slant max = {sc_max} NM")

    # Receiver marker
    ax.scatter([0], [0], color="red", s=80, zorder=6)
    ax.annotate("Rx", (0, 0), xytext=(gd_max * 0.02, alt_max_ft / 1000 * 0.03),
                color="red", fontsize=9)

    ax.set_xlim(0, gd_max)
    ax.set_ylim(0, alt_max_ft / 1000)
    ax.set_xlabel("Ground Distance (NM)", fontsize=10)
    ax.set_ylabel("Relative Altitude (1000 ft)", fontsize=10)
    ax.set_title("Cross-Section  (radially symmetric about vertical axis)", fontsize=10)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)


# ---------------------------------------------------------------------------
# 3-D revolved surface
# ---------------------------------------------------------------------------

def plot3dVolume(ax, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max,
                 gd_max, alt_max_ft, N_z=200, N_r=400, N_theta=72):
    """Plot the tracking volume as a surface of revolution of the cross-section."""

    alt_vals = np.linspace(0, alt_max_ft, N_z)
    r_sample = np.linspace(0, gd_max, N_r)
    theta = np.linspace(0, 2 * math.pi, N_theta)

    # For each altitude slice find inner and outer valid r
    inner_r = np.full(N_z, np.nan)
    outer_r = np.full(N_z, np.nan)

    for iz, alt in enumerate(alt_vals):
        alt_arr = np.full(N_r, alt)
        valid = inVolume(r_sample, alt_arr,
                         gc_min, gc_max, sc_min, sc_max, alt_min, alt_max)
        if valid.any():
            first = int(np.argmax(valid))
            last = int(N_r - 1 - np.argmax(valid[::-1]))
            inner_r[iz] = r_sample[first]
            outer_r[iz] = r_sample[last]

    valid_idx = np.where(~np.isnan(outer_r))[0]
    if len(valid_idx) == 0:
        ax.set_title("No valid volume with these constraints")
        return

    surf_color = "steelblue"
    alpha = 0.35

    # Helper: revolve a 1-D radial profile around z-axis
    def addSurface(r_profile, z_profile):
        T, Zi = np.meshgrid(theta, np.arange(len(z_profile)))
        R = r_profile[Zi]
        Z = z_profile[Zi] / 1000
        X = R * np.cos(T)
        Y = R * np.sin(T)
        ax.plot_surface(X, Y, Z, color=surf_color, alpha=alpha, linewidth=0,
                        antialiased=False)

    # Helper: add a horizontal (cap) disk at a given altitude slice
    def addCap(iz):
        r_in = inner_r[iz] if not np.isnan(inner_r[iz]) else 0.0
        r_out = outer_r[iz]
        if np.isnan(r_out):
            return
        r_cap = np.linspace(r_in, r_out, 30)
        T_cap, R_cap = np.meshgrid(theta, r_cap)
        X_cap = R_cap * np.cos(T_cap)
        Y_cap = R_cap * np.sin(T_cap)
        Z_cap = np.full_like(X_cap, alt_vals[iz] / 1000)
        ax.plot_surface(X_cap, Y_cap, Z_cap, color=surf_color, alpha=alpha,
                        linewidth=0, antialiased=False)

    # Outer wall
    addSurface(outer_r[valid_idx], alt_vals[valid_idx])

    # Inner wall (only where there is a genuine inner boundary > 0)
    has_inner = valid_idx[inner_r[valid_idx] > 1e-3]
    if len(has_inner) > 0:
        addSurface(inner_r[has_inner], alt_vals[has_inner])

    # Bottom cap
    addCap(valid_idx[0])
    # Top cap (only if different from bottom)
    if valid_idx[-1] != valid_idx[0]:
        addCap(valid_idx[-1])

    # Receiver marker
    ax.scatter([0], [0], [0], color="red", s=100, zorder=6, label="Receiver")

    lim = gd_max
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_zlim(0, alt_max_ft / 1000)
    ax.set_xlabel("X (NM)", fontsize=9)
    ax.set_ylabel("Y (NM)", fontsize=9)
    ax.set_zlabel("Rel. Alt. (1000 ft)", fontsize=9)
    ax.set_title("3-D Tracking Volume", fontsize=10)
    ax.legend(fontsize=8)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parseArgs()

    gc_min = gc_max = sc_min = sc_max = alt_min = alt_max = None

    # Load from config file first (lowest priority)
    if args.configFilePath:
        cfg = loadConfig(args.configFilePath)
        gc_min, gc_max = extractMinmax(cfg.get("groundDistance"))
        sc_min, sc_max = extractMinmax(cfg.get("slantDistance"))
        alt_min, alt_max = extractMinmax(cfg.get("altitude"))

    # CLI overrides config
    if args.groundDistance:
        gc_min, gc_max = args.groundDistance
    if args.slantDistance:
        sc_min, sc_max = args.slantDistance
    if args.altitude:
        alt_min, alt_max = args.altitude

    if all(v is None for v in [gc_min, gc_max, sc_min, sc_max, alt_min, alt_max]):
        print("No constraints specified.  Use -g, -s, -a, or -c.  See --help.")
        sys.exit(1)

    gd_max, alt_max_ft = getPlotBounds(gc_min, gc_max, sc_min, sc_max, alt_min, alt_max)

    # Build a descriptive title
    parts = []
    if gc_min is not None or gc_max is not None:
        lo = f"{gc_min}" if gc_min is not None else "−∞"
        hi = f"{gc_max}" if gc_max is not None else "+∞"
        parts.append(f"Ground [{lo}, {hi}] NM")
    if sc_min is not None or sc_max is not None:
        lo = f"{sc_min}" if sc_min is not None else "−∞"
        hi = f"{sc_max}" if sc_max is not None else "+∞"
        parts.append(f"Slant [{lo}, {hi}] NM")
    if alt_min is not None or alt_max is not None:
        lo = f"{alt_min:,.0f}" if alt_min is not None else "−∞"
        hi = f"{alt_max:,.0f}" if alt_max is not None else "+∞"
        parts.append(f"Alt [{lo}, {hi}] ft")
    title = "adsbmon Tracking Volume  ·  " + "   |   ".join(parts)

    fig = plt.figure(figsize=(15, 7))
    fig.suptitle(title, fontsize=11)

    ax2d = fig.add_subplot(1, 2, 1)
    plotCrossSection(ax2d, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max,
                     gd_max, alt_max_ft)

    ax3d = fig.add_subplot(1, 2, 2, projection="3d")
    plot3dVolume(ax3d, gc_min, gc_max, sc_min, sc_max, alt_min, alt_max,
                 gd_max, alt_max_ft)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


if __name__ == "__main__":
    main()
