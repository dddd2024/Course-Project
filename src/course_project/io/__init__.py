"""Input normalization (Track D): raw bytes -> project-native ByteStream."""

from course_project.io.loaders import InputError, load_bin, load_dat, load_raw
from course_project.io.metadata import input_metadata
from course_project.io.records import ByteStream, InputFormat

__all__ = [
    "ByteStream",
    "InputError",
    "InputFormat",
    "input_metadata",
    "load_bin",
    "load_dat",
    "load_raw",
]
