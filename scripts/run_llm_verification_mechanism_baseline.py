from __future__ import annotations

import argparse
from pathlib import Path

from course_project.experiments import (
    run_llm_verification_mechanism_baseline,
    write_llm_verification_mechanism_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Execute the synthetic LLM + deterministic verification mechanism baseline "
            "without provenance fusion or teacher-data claims."
        )
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    args = parser.parse_args()

    execution = run_llm_verification_mechanism_baseline(
        args.outdir / "work" / "llm-verification",
        code_sha=args.code_sha,
    )
    records = write_llm_verification_mechanism_execution(
        execution,
        args.outdir / "records",
    )

    print(f"dataset={execution.corpus.dataset.dataset_id}")
    print(f"sha256={execution.corpus.dataset.sha256}")
    print(f"variant={execution.record.variant}")
    print(f"records={records}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
