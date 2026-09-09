from __future__ import annotations

import argparse
import json
from pathlib import Path

from course_project.experiments.external_pre import (
    run_live_netzob_mechanism_experiment,
    write_netzob_experiment_bundle,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execute the pinned live Netzob mechanism baseline and write ExperimentRecord evidence."
    )
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    bundle = run_live_netzob_mechanism_experiment(code_sha=args.code_sha)
    out_dir = write_netzob_experiment_bundle(bundle, args.outdir)
    parse_coverage = next(
        metric for metric in bundle.record.metrics if metric.name == "parse_coverage"
    )
    print(
        json.dumps(
            {
                "backend": bundle.record.config["backend"],
                "backendVersion": bundle.record.config["backendVersion"],
                "candidateCount": len(bundle.field_candidates),
                "datasetId": bundle.record.dataset.dataset_id,
                "outdir": str(out_dir),
                "parseCoverage": parse_coverage.value,
                "resultScope": bundle.record.result_scope,
                "variant": bundle.record.variant,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
