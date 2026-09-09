from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments import (
    run_full_evidencegraph_mechanism_experiment,
    write_full_evidencegraph_mechanism_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the full EvidenceGraph-PRE production architecture as "
            "synthetic mechanism evidence without teacher-data or real-LLM claims."
        )
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args()

    execution = run_full_evidencegraph_mechanism_experiment(
        args.outdir / "full-method-work",
        code_sha=args.code_sha,
    )
    records_dir = write_full_evidencegraph_mechanism_execution(
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
