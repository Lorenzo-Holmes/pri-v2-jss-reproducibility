"""Recalculate the manuscript tables from retained study records."""
from pathlib import Path
import argparse
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    out = ap.parse_args().output.resolve()
    if out.exists():
        raise SystemExit("Use a fresh output directory.")
    out.mkdir(parents=True)
    jobs = [
        ("reconstruct_records.py", ["--output-dir", str(out/"reconstruction")]),
        ("analyze_records.py", ["--output", str(out/"secondary_analysis")]),
        ("candidate_tables.py", ["--output", str(out/"candidate_analysis")]),
        ("compare_effects.py", ["--output", str(out/"effect_comparison")]),
        ("analyze_ranks.py", ["--output", str(out/"rank_analysis")]),
        ("make_publication_tables.py", ["--analysis", str(out)]),
    ]
    for script, args in jobs:
        subprocess.run([sys.executable, "-B", str(ROOT/"analysis"/script), *args], check=True)
    print("Tables written to", out)
if __name__ == "__main__":
    main()
