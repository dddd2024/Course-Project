# Teacher-data ingress and ground-truth isolation

This contract prepares the project for the teacher-provided .dat file without
claiming that the authoritative dataset has been received or evaluated. Synthetic
inputs use the same registration and analysis interface, but remain engineering
fixtures.

## Boundary

Inference receives only registered raw bytes plus the canonical Sidecar analysis
configuration. The sequence is:

    local .dat path -> register_input -> opaque inputRef -> inspect_file/analyze

register_input records the basename, byte size, kind, and SHA-256 digest. analyze
accepts inputRef, mode, stage/feature switches, timeout, and optional dependency
policy. The Sidecar contract rejects unknown keys. Track D also rejects
evaluation-only keys such as groundTruthRef, labels, answerKey, or expectedProtocol,
including when a caller invokes the backend directly.

Ground truth is loaded separately by evaluation/experiment code after inference has
produced immutable result artifacts. DatasetIdentity.ground_truth declares which
metrics are evaluable; metrics without the required ground truth fail closed instead
of receiving fabricated values. A ground-truth reference must never be copied into
an analyze request or semantic-backend configuration.

## Sanitized metadata contract

Record one JSON object that validates against
contracts/teacher-dataset-metadata.schema.json:

- datasetId, version, sha256, and sizeBytes identify the exact input;
- corpusKind distinguishes teacher, synthetic, and other corpora;
- receivedAt records receipt time when applicable;
- redistributionStatus is prohibited, permitted, or unknown;
- preprocessing records transformations, using none when bytes are unchanged;
- groundTruth is null when absent, or contains a local evaluation-only reference,
  its digest, and the capabilities actually supplied.

The metadata contains no raw packet bytes, labels, answers, or absolute source path.
The local source path is used only for register_input. Raw teacher data and answer
files stay outside Git unless redistribution permission is explicitly recorded as
permitted; .dat, .bin, PCAP, raw data directories, outputs, and results are ignored
by default.

## Procedure when teacher data arrives

From a clean checkout and activated Python 3.10 or 3.11 environment:

1. Put the .dat and any answer file in an external local directory. Do not place
   them under a tracked fixture directory.
2. Capture identity without modifying the data:

       Get-FileHash -Algorithm SHA256 C:\external-data\teacher.dat
       (Get-Item C:\external-data\teacher.dat).Length

3. Create a sanitized metadata JSON from the schema above. Record the supplied
   version/date, redistribution decision, preprocessing, and only the available
   ground-truth capability names.
4. Run python -m course_project.doctor, then select the file in the desktop app or
   submit the unchanged Sidecar sequence register_input, inspect_file, analyze, and
   get_result. No source-code or protocol change is required.
5. Preserve analysis-result.json and its referenced artifacts before opening any
   answer file. Record the Git SHA, Python/dependency versions, analysis config,
   start/end time, and failure/limitation status.
6. Run the experiment/evaluation command with the separate ground-truth reference.
   Report only metrics supported by its declared capabilities; mark all others not
   evaluable.
7. Before sharing artifacts, enforce redistributionStatus. Hashes and aggregate
   metrics may be recorded; raw bytes and answer contents remain external unless
   permission is permitted.

## Pre-data dry run and evidence

The checked-in synthetic placeholder goes through the real JSONL process entrypoint,
not an in-process mock:

    python -m pytest -q tests/test_sidecar_process.py tests/test_teacher_data_ingress.py tests/test_sidecar_runtime.py

test_synthetic_placeholder_uses_final_teacher_data_ingress_without_labels creates a
temporary .dat, registers and hashes it, invokes analysis, fetches the result, and
checks message, alignment, statistics, behavior, evidence, and schema artifacts. The
label-leakage tests prove that both the public request boundary and direct Track D
backend reject evaluation-only configuration. This demonstrates ingress readiness;
it is not teacher-data E2E evidence or a benchmark result.

For the real run, attach the following sanitized evidence to the final tracker:

    git SHA:
    Windows/Python versions:
    dataset ID/version/SHA-256/size:
    redistribution status:
    ground-truth capabilities (or none):
    command/config:
    result artifact reference + SHA-256:
    limitations/failures:

Related gates: #6, #7, #15, #99, and #101.
