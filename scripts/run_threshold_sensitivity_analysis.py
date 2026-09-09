from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments.threshold_sensitivity import (
    run_threshold_sensitivity_analysis,
    write_threshold_sensitivity_execution,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute the deterministic EvidenceGraph-PRE fusion-threshold sensitivity grid."
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    execution = run_threshold_sensitivity_analysis(
        args.outdir / "threshold-sensitivity-work",
        code_sha=args.code_sha,
    )
    records_dir = args.outdir / "records"
    write_threshold_sensitivity_execution(execution, records_dir)
    print(records_dir / "threshold_sensitivity.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
