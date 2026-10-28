"""Seeded random generators: one stream per (run seed, component), as SPEC §2 requires.

A component is a stable name such as "population" or "dispensing". Python's hash() is salted per
process, so the name is turned into a number with CRC-32, which is the same on every machine.
"""

import zlib

import numpy as np


def component_rng(seed: int, component: str) -> np.random.Generator:
    return np.random.default_rng([seed, zlib.crc32(component.encode("utf-8"))])
