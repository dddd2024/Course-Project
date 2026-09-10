"""Download/verify the pinned public corpus and write sanitized evidence."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from course_project.experiments import materialize_public_corpus, write_public_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, default=Path("data/raw/nfstream-public"))
    parser.add_argument("--work-dir", type=Path, default=Path("outputs/public-benchmark"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("deliverables/public-benchmark"),
    )
    parser.add_argument("--code-sha", default=None)
    args = parser.parse_args()
    code_sha = args.code_sha or subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    corpus = materialize_public_corpus(args.corpus_dir)
    output = write_public_benchmark(
        corpus,
        args.work_dir,
        args.output_dir,
        code_sha=code_sha,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
