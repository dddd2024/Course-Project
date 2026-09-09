from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments import (
    run_no_provenance_ablation,
    write_no_provenance_ablation_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the no-provenance EvidenceGraph-PRE ablation as synthetic "
            "mechanism evidence without teacher-data or real-LLM claims."
        )
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args()

    execution = run_no_provenance_ablation(
        args.outdir / "no-provenance-work",
        code_sha=args.code_sha,
    )
    records_dir = write_no_provenance_ablation_execution(
        execution,
        args.outdir / "records",
    )

    print(f"dataset={execution.corpus.dataset.dataset_id}")
    print(f"sha256={execution.corpus.dataset.sha256}")
    print(f"variant={execution.record.variant}")
    print(f"provider={execution.record.model_provider}")
    print(f"model_version={execution.record.model_version}")
    print(f"records={records_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
