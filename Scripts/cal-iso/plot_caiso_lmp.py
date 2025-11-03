#!/usr/bin/env python3
"""
Plot California ISO LMP CSV (e.g., DAM LMP) with robust handling for large files.

Examples:
  ./plot_caiso_lmp.py data.csv --save out.png
  ./plot_caiso_lmp.py data.csv --node 0096WD_7_N001
  ./plot_caiso_lmp.py data.csv --node 0096WD_7_N001,ABC123 --resample 15min
  ./plot_caiso_lmp.py data.csv --market DAM --aggregate mean --resample 1H
  ./plot_caiso_lmp.py data.csv --chunksize 10000 --simplify-threshold 0.5 --save out.png
"""

import argparse
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from typing import List, Optional

def parse_args():
    p = argparse.ArgumentParser(description="Plot CAISO LMP CSV with filtering and safe large-plot handling.")
    p.add_argument("csv", help="Path to CAISO LMP CSV.")
    p.add_argument("--node", help="Filter by NODE_ID. Comma-separated for multiple.")
    p.add_argument("--market", help="Filter by MARKET_RUN_ID (e.g., DAM, RTM).")
    p.add_argument("--lmp-type", help="Filter by LMP_TYPE (e.g., LMP, MCC, MLC).")
    p.add_argument("--start", help="Start datetime ISO (e.g., 2025-10-01T00:00).")
    p.add_argument("--end", help="End datetime ISO (e.g., 2025-10-02T00:00).")

    # Rendering controls
    p.add_argument("--aggregate", choices=["none","mean","median"], default="mean",
                   help="If multiple nodes are present *and* --node is not given: "
                        "aggregate across nodes per timestamp. Default: mean.")
    p.add_argument("--resample", help="Optional pandas offset alias to resample (e.g. 15min, 1H).")
    p.add_argument("--scatter", action="store_true",
                   help="Force scatter instead of line (useful for huge datasets).")
    p.add_argument("--chunksize", type=int, default=20000,
                   help="matplotlib Agg path chunk size to avoid overflow (0 disables).")
    p.add_argument("--simplify-threshold", type=float, default=0.5,
                   help="Path simplify threshold (higher = more aggressive).")
    p.add_argument("--title", help="Custom plot title.")
    p.add_argument("--save", help="Path to save image (e.g. plot.png). If omitted, shows window.")
    return p.parse_args()

def maybe_split_nodes(node_arg: Optional[str]) -> Optional[List[str]]:
    if not node_arg:
        return None
    return [x.strip() for x in node_arg.split(",") if x.strip()]

def main():
    args = parse_args()

    # Safer defaults for large paths
    if args.chunksize is not None:
        mpl.rcParams["agg.path.chunksize"] = int(args.chunksize)  # e.g., 20000
    mpl.rcParams["path.simplify"] = True
    mpl.rcParams["path.simplify_threshold"] = float(args.simplify_threshold)

    # Load
    df = pd.read_csv(args.csv)

    # Expected columns exist?
    required_cols = {
        "INTERVALSTARTTIME_GMT", "INTERVALENDTIME_GMT", "MARKET_RUN_ID",
        "LMP_TYPE", "NODE_ID", "MW"
    }
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"Missing columns in CSV: {', '.join(sorted(missing))}")

    # Parse times
    df["ts"] = pd.to_datetime(df["INTERVALSTARTTIME_GMT"], errors="coerce")
    df = df.dropna(subset=["ts"])

    # Filters
    nodes = maybe_split_nodes(args.node)
    if nodes:
        df = df[df["NODE_ID"].isin(nodes)]
    if args.market:
        df = df[df["MARKET_RUN_ID"].str.upper() == args.market.upper()]
    if args.lmp_type:
        df = df[df["LMP_TYPE"].str.upper() == args.lmp_type.upper()]
    if args.start:
        df = df[df["ts"] >= pd.to_datetime(args.start)]
    if args.end:
        df = df[df["ts"] <= pd.to_datetime(args.end)]

    if df.empty:
        raise SystemExit("No data after filtering. Check filters or input file.")

    # Sort by time before plotting
    df = df.sort_values("ts")

    # Resample helper (works after setting index)
    def apply_resample(frame: pd.DataFrame) -> pd.DataFrame:
        if not args.resample:
            return frame
        # Mean over the resample window
        return (
            frame.set_index("ts")["MW"]
                 .resample(args.resample)
                 .mean()
                 .dropna()
                 .reset_index()
        )

    plt.figure(figsize=(12, 6))

    # If user specified nodes, plot each separately
    if nodes:
        for nid, g in df.groupby("NODE_ID", sort=False):
            g = g[["ts","MW"]]
            g = apply_resample(g) if args.resample else g
            if args.scatter:
                plt.scatter(g["ts"], g["MW"], s=6, alpha=0.7, label=nid)
            else:
                plt.plot(g["ts"], g["MW"], marker=None, linestyle="-", label=nid)
        legend_label = "Selected nodes"
    else:
        # No explicit nodes. If there are multiple nodes present, aggregate per timestamp
        n_nodes = df["NODE_ID"].nunique()
        if n_nodes > 1 and args.aggregate != "none":
            # Aggregate across nodes at each timestamp
            agg_fn = {"mean": "mean", "median": "median"}[args.aggregate]
            agg_series = df.groupby("ts")["MW"].agg(agg_fn).reset_index()
            agg_series = apply_resample(agg_series) if args.resample else agg_series
            if args.scatter:
                plt.scatter(agg_series["ts"], agg_series["MW"], s=6, alpha=0.7)
            else:
                plt.plot(agg_series["ts"], agg_series["MW"], marker=None, linestyle="-")
            legend_label = f"{args.aggregate.title()} across {n_nodes} nodes"
        else:
            # Single node in data (or user chose aggregate=none) — plot raw (or resampled) series
            series = df[["ts","MW"]]
            series = apply_resample(series) if args.resample else series
            if args.scatter:
                plt.scatter(series["ts"], series["MW"], s=6, alpha=0.7)
            else:
                plt.plot(series["ts"], series["MW"], marker=None, linestyle="-")
            legend_label = "Series"

    # Labels & title
    plt.xlabel("Time (GMT)")
    plt.ylabel("LMP ($/MWh)")
    base_title = args.title or "CAISO LMP"
    sub_bits = []
    if args.market: sub_bits.append(args.market.upper())
    if args.lmp_type: sub_bits.append(args.lmp_type.upper())
    if nodes: sub_bits.append(f"nodes={','.join(nodes)}")
    if args.resample: sub_bits.append(f"resample={args.resample}")
    if args.aggregate and (not nodes): sub_bits.append(f"aggregate={args.aggregate}")
    subtitle = " | ".join(sub_bits)
    plt.title(f"{base_title}" + (f" — {subtitle}" if subtitle else ""))
    if nodes or (not nodes and legend_label):
        # Only show legend if there are multiple lines (or a meaningful label)
        if nodes and len(nodes) > 1:
            plt.legend(title=legend_label)
        elif nodes is None and "across" in legend_label:
            plt.legend([legend_label])

    plt.grid(True)
    plt.tight_layout()

    # Heuristic: if path still too big, user can set --scatter or lower sampling
    # (no additional action here—rcParams are already applied)

    if args.save:
        plt.savefig(args.save, dpi=150)
        print(f"Saved plot to {args.save}")
    else:
        plt.show()

if __name__ == "__main__":
    main()

