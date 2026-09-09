from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments import (
    run_synthetic_mechanism_experiments,
    write_experiment_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute synthetic mechanism experiments without teacher-data claims."
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args()

    work_dir = args.outdir / "work"
    bundle = run_synthetic_mechanism_experiments(work_dir, code_sha=args.code_sha)
    write_experiment_bundle(bundle, args.outdir / "records")

    print(f"dataset={bundle.corpus.dataset.dataset_id}")
    print(f"sha256={bundle.corpus.dataset.sha256}")
    print("variants=" + ",".join(record.variant for record in bundle.records))
    print(f"records={args.outdir / 'records'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
