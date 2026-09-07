"""Input normalization (Track D): raw bytes -> project-native ByteStream."""

from course_project.io.loaders import InputError, load_bin, load_dat, load_raw
from course_project.io.records import ByteStream, InputFormat

__all__ = [
    "ByteStream",
    "InputError",
    "InputFormat",
    "load_bin",
    "load_dat",
    "load_raw",
]
