"""Synthetic ground-truth dataset generator (Track D).

Generates three controlled datasets as defined in ``docs/design-v1.md``
section 8, with ground truth kept in separate sidecar files (analysis input
and answers are never mixed; ``docs/testing-plan.md`` section 2). The generator
is fully deterministic: the same seed produces the same bytes and the same
sidecars. Outputs are engineering fixtures only — they must not be presented
as teacher-provided results.

    Dataset A - plain binary protocol, two message types, text-like payload
    Dataset B - plain header + payload encrypted with a toy XOR keystream
    Dataset C - three behavior flows (heartbeat / download / upload) with
                encrypted payloads plus direction/timestamp metadata

The "encryption" is a seeded XOR keystream used only to shape payload entropy
for the analysis pipeline. It is NOT real cryptography and makes no security
claim (see the scientific boundaries in ``AGENTS.md``).

Usage:

    python examples/generate_synthetic_datasets.py --outdir synthetic-datasets

Output layout:

    <outdir>/manifest.json
    <outdir>/dataset-a/{capture.dat, ground_truth.json}
    <outdir>/dataset-b/{capture.dat, ground_truth.json}
    <outdir>/dataset-c/{flow-*.dat, flow-*.meta.json, flows.json}

Message layout shared by all datasets (header = 11 bytes):

    magic(4) type(1) reserved(3) seq(1) length(2, BE, = total) payload(...)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

GENERATOR_VERSION = 1
MAGIC = b"SYN1"
HEADER_LEN = 11  # magic(4) + type(1) + reserved(3) + seq(1) + length(2)


def _plain_payload(rng: random.Random, length: int) -> bytes:
    """Deterministic text-like bytes (printable ASCII)."""
    return bytes(rng.randint(0x20, 0x7E) for _ in range(length))


def _xor_keystream(rng: random.Random, payload: bytes) -> bytes:
    """Toy XOR stream cipher for entropy shaping only (NOT real crypto)."""
    keystream = rng.randbytes(len(payload))
    return bytes(a ^ b for a, b in zip(payload, keystream))


def _build_message(
    msg_type: int, seq: int, payload: bytes, cipher_rng: random.Random | None
) -> bytes:
    if cipher_rng is not None:
        payload = _xor_keystream(cipher_rng, payload)
    total = HEADER_LEN + len(payload)
    if total > 0xFFFF:
        raise ValueError("message longer than the 2-byte length field supports")
    return (
        MAGIC
        + bytes([msg_type])
        + b"\x00\x00\x00"
        + bytes([seq])
        + total.to_bytes(2, "big")
        + payload
    )


def _schema(dataset_id: str, type_semantic: str) -> list[dict]:
    return [
        {"name": "magic", "offset": 0, "size": 4, "semantic_type": "magic"},
        {"name": "type", "offset": 4, "size": 1, "semantic_type": type_semantic},
        {"name": "reserved", "offset": 5, "size": 3, "semantic_type": "constant"},
        {"name": "seq", "offset": 8, "size": 1, "semantic_type": "sequence"},
        {
            "name": "length",
            "offset": 9,
            "size": 2,
            "semantic_type": "length",
            "endian": "big",
            "match": "total",
        },
        {
            "name": "payload",
            "offset": HEADER_LEN,
            "size": None,
            "semantic_type": "payload",
        },
    ]


def _ground_truth(
    dataset_id: str,
    messages: list[bytes],
    sha256: str,
    seed: int,
    *,
    type_semantic: str,
    flow: dict | None = None,
    payload_cipher: dict | None = None,
) -> dict:
    boundaries = [0]
    records = []
    offset = 0
    for index, message in enumerate(messages):
        end = offset + len(message)
        records.append(
            {
                "index": index,
                "start": offset,
                "end": end,
                "type": message[4],
                "seq": message[8],
                "length": int.from_bytes(message[9:11], "big"),
            }
        )
        boundaries.append(end)
        offset = end
    return {
        "dataset_id": dataset_id,
        "generator": "examples/generate_synthetic_datasets.py",
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "sha256": sha256,
        "schema": _schema(dataset_id, type_semantic),
        "messages": records,
        "boundaries": boundaries,
        "flow": flow,
        "payload_cipher": payload_cipher,
    }


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_dataset(
    outdir: Path,
    dataset_id: str,
    messages: list[bytes],
    seed: int,
    type_semantic: str,
    **gt_extra: dict,
) -> dict:
    dataset_dir = outdir / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=True)
    capture = b"".join(messages)
    capture_path = dataset_dir / "capture.dat"
    capture_path.write_bytes(capture)
    sha256 = hashlib.sha256(capture).hexdigest()
    gt = _ground_truth(
        dataset_id, messages, sha256, seed, type_semantic=type_semantic, **gt_extra
    )
    _write_json(dataset_dir / "ground_truth.json", gt)
    return {"dataset_id": dataset_id, "dir": dataset_id, "sha256": sha256,
            "message_count": len(messages)}


def _write_flow(
    flows_dir: Path,
    dataset_id: str,
    flow_name: str,
    messages: list[bytes],
    directions: list[str],
    timestamps: list[float],
    behavior_label: str,
    seed: int,
) -> dict:
    capture = b"".join(messages)
    capture_path = flows_dir / f"{flow_name}.dat"
    capture_path.write_bytes(capture)
    sha256 = hashlib.sha256(capture).hexdigest()
    flow = {
        "label": behavior_label,
        "directions": directions,
        "timestamps": timestamps,
    }
    gt = _ground_truth(
        dataset_id,
        messages,
        sha256,
        seed,
        type_semantic="constant",
        flow=flow,
        payload_cipher={"scheme": "xor_keystream", "seed": seed},
    )
    _write_json(flows_dir / f"{flow_name}.meta.json", gt)
    return {"flow": flow_name, "sha256": sha256, "label": behavior_label,
            "message_count": len(messages)}


def generate(outdir: Path, seed: int) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    datasets = []

    # ---- Dataset A: plain protocol, two message types, text-like payload ----
    rng = random.Random(seed)
    messages_a = []
    for msg_type in (0x01, 0x02):
        for seq in range(1, 11):
            payload = _plain_payload(rng, rng.randrange(0, 41))
            messages_a.append(_build_message(msg_type, seq, payload, None))
    datasets.append(_write_dataset(outdir, "dataset-a", messages_a, seed, "enum"))

    # ---- Dataset B: one type, encrypted payload ----
    rng = random.Random(seed + 1)
    cipher_rng = random.Random(seed + 100)
    messages_b = []
    for seq in range(1, 21):
        payload = _plain_payload(rng, rng.randrange(0, 41))
        messages_b.append(_build_message(0x01, seq, payload, cipher_rng))
    datasets.append(_write_dataset(
        outdir, "dataset-b", messages_b, seed + 1, "constant",
        payload_cipher={"scheme": "xor_keystream", "seed": seed + 100},
    ))

    # ---- Dataset C: three behavior flows with encrypted payloads ----
    flows_dir = outdir / "dataset-c"
    flows_dir.mkdir(parents=True, exist_ok=True)
    flows = []

    rng = random.Random(seed + 2)
    cipher_rng = random.Random(seed + 200)
    messages = []
    for seq in range(1, 13):
        payload = _plain_payload(rng, rng.randrange(4, 9))
        messages.append(_build_message(0x01, seq, payload, cipher_rng))
    directions = ["up" if i % 2 == 0 else "down" for i in range(12)]
    timestamps = [i * 5.0 for i in range(12)]
    flows.append(_write_flow(flows_dir, "synthetic-c-heartbeat", "flow-heartbeat",
                             messages, directions, timestamps, "HEARTBEAT", seed + 200))

    rng = random.Random(seed + 3)
    cipher_rng = random.Random(seed + 300)
    messages = []
    for seq in range(1, 13):
        payload = _plain_payload(rng, rng.randrange(512, 1025))
        messages.append(_build_message(0x02, seq, payload, cipher_rng))
    directions = ["up"] * 2 + ["down"] * 10
    timestamps = []
    clock = 0.0
    for _ in range(12):
        clock += rng.uniform(1.0, 3.0)
        timestamps.append(round(clock, 3))
    flows.append(_write_flow(flows_dir, "synthetic-c-download", "flow-download",
                             messages, directions, timestamps, "DOWNLOAD", seed + 300))

    rng = random.Random(seed + 4)
    cipher_rng = random.Random(seed + 400)
    messages = []
    for seq in range(1, 13):
        payload = _plain_payload(rng, rng.randrange(512, 1025))
        messages.append(_build_message(0x03, seq, payload, cipher_rng))
    directions = ["down"] * 2 + ["up"] * 10
    timestamps = []
    clock = 0.0
    for _ in range(12):
        clock += rng.uniform(1.0, 3.0)
        timestamps.append(round(clock, 3))
    flows.append(_write_flow(flows_dir, "synthetic-c-upload", "flow-upload",
                             messages, directions, timestamps, "UPLOAD", seed + 400))

    _write_json(flows_dir / "flows.json", {"dataset_id": "synthetic-c", "flows": flows})
    datasets.append({"dataset_id": "synthetic-c", "dir": "dataset-c",
                     "flows": flows})

    _write_json(outdir / "manifest.json", {
        "generator": "examples/generate_synthetic_datasets.py",
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "note": (
            "Engineering-only synthetic fixtures (testing-plan section 2); "
            "NOT teacher-provided evaluation data."
        ),
        "datasets": datasets,
    })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", default="synthetic-datasets",
                        help="output directory (default: %(default)s)")
    parser.add_argument("--seed", type=int, default=20260907,
                        help="deterministic seed (default: %(default)s)")
    args = parser.parse_args(argv)
    generate(Path(args.outdir), args.seed)
    print(f"generated datasets in {args.outdir} (seed={args.seed})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
