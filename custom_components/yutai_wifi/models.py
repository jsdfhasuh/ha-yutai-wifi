"""Explicit, reviewed model profiles. Unknown models never inherit a mapping."""

from dataclasses import dataclass
import math
from types import MappingProxyType


@dataclass(frozen=True)
class Property:
    key: str
    siid: int
    piid: int
    kind: type
    minimum: float = 0
    maximum: float = 65535

    def valid(self, value) -> bool:
        if self.kind is bool:
            return type(value) is bool
        if self.kind is int and type(value) is not int:
            return False
        if type(value) not in (int, float):
            return False
        return math.isfinite(value) and self.minimum <= value <= self.maximum


@dataclass(frozen=True)
class ModelProfile:
    model: str
    name: str
    properties: tuple[Property, ...]


JDLS1 = ModelProfile(
    model="yutai.plug.jdls1",
    name="Yutai JDLS1",
    properties=(
        Property("relay", 2, 1, bool),
        Property("energy", 3, 1, float),
        Property("power", 3, 2, int, maximum=10000),
        Property("current", 3, 4, float),
        Property("voltage", 3, 5, int),
    ),
)
PROFILES = MappingProxyType({JDLS1.model: JDLS1})
