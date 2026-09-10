"""Input normalization (Track D): raw bytes -> project-native ByteStream."""

from course_project.io.containers import detect_container
from course_project.io.loaders import InputError, load_bin, load_dat, load_raw
from course_project.io.metadata import input_metadata
from course_project.io.preprocess import PreprocessResult, preprocess
from course_project.io.protocols import DtlsRecord, classify_transport, parse_dtls_record
from course_project.io.records import ByteStream, InputFormat
from course_project.io.scapy_adapter import (
    ExtractedPacket,
    PcapExtractionResult,
    extract_packets,
    is_scapy_available,
)

__all__ = [
    "ByteStream",
    "DtlsRecord",
    "ExtractedPacket",
    "InputError",
    "InputFormat",
    "PcapExtractionResult",
    "PreprocessResult",
    "classify_transport",
    "detect_container",
    "extract_packets",
    "input_metadata",
    "is_scapy_available",
    "load_bin",
    "load_dat",
    "load_raw",
    "parse_dtls_record",
    "preprocess",
]
