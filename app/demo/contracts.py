"""Public value objects and errors shared by the Demo CLI and lifecycle."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

AllowedPermission = Literal["knowledge.read", "case.read"]
PermissionAction = Literal["revoke", "restore"]


class DemoError(RuntimeError):
    """A safe, user-facing failure in a development Demo command."""


@dataclass(frozen=True)
class DemoIdentity:
    username: str
    password: str


@dataclass(frozen=True)
class DemoCase:
    case_id: str
    case_no: str
    form_id: str


@dataclass(frozen=True)
class DemoSeedResult:
    command: Literal["seed"]
    case: DemoCase
    appraiser: DemoIdentity
    reviewer: DemoIdentity
    inspector: DemoIdentity
    questions: dict[str, str]
    urls: dict[str, str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


__all__ = [
    "AllowedPermission",
    "PermissionAction",
    "DemoError",
    "DemoIdentity",
    "DemoCase",
    "DemoSeedResult",
]
