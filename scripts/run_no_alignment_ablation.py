from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments.no_alignment import (
    run_no_alignment_ablation,
    write_no_alignment_ablation_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the deterministic alignment-evidence EvidenceGraph-PRE ablation."
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args()

    execution = run_no_alignment_ablation(
        args.outdir / "work" / "no-alignment",
        code_sha=args.code_sha,
    )
    write_no_alignment_ablation_execution(execution, args.outdir / "records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
