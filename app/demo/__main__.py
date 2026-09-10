"""Safe command-line composition root for the development Demo lifecycle."""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.core.config import get_settings

from .contracts import DemoError

_ALLOWED_PERMISSION_CODES = ("knowledge.read", "case.read")
_PERMISSION_ACTIONS = ("revoke", "restore")
_ENVELOPE_KEYS = frozenset({"ok", "error"})
_FORBIDDEN_STATUS_KEY = re.compile(
    r"password|token|jwt|bucket|object_key|presigned",
    re.IGNORECASE,
)

Handler = Callable[..., object]
Handlers = Mapping[str, Handler]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally small, allowlisted Demo command surface."""

    parser = argparse.ArgumentParser(description="Manage the development Demo lifecycle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("seed", "status", "reset"):
        subparsers.add_parser(command)

    permission = subparsers.add_parser("permission")
    permission_actions = permission.add_subparsers(dest="action", required=True)
    for action in _PERMISSION_ACTIONS:
        action_parser = permission_actions.add_parser(action)
        action_parser.add_argument(
            "permission_code",
            choices=_ALLOWED_PERMISSION_CODES,
        )

    return parser.parse_args(argv)


def _ensure_development() -> None:
    """Reject every Demo command outside the development environment."""

    if get_settings().app_env != "development":
        raise DemoError("DEVELOPMENT_ONLY: demo commands require APP_ENV=development")


def _default_handlers() -> dict[str, Handler]:
    """Resolve lifecycle implementations only after the environment gate."""

    # Keep imports lazy so the exact development gate in ``main`` runs before
    # PostgreSQL/MinIO clients or lifecycle modules are resolved.
    def seed() -> object:
        from app.demo.lifecycle import seed as lifecycle_seed

        return lifecycle_seed()

    def status() -> object:
        from app.demo.lifecycle import status as lifecycle_status

        return lifecycle_status()

    def reset() -> object:
        from app.demo.lifecycle import reset as lifecycle_reset

        return lifecycle_reset()

    def permission(action: str, permission_code: str) -> object:
        from app.demo.permission import permission_command

        return permission_command(action, permission_code)

    return {
        "seed": seed,
        "status": status,
        "reset": reset,
        "permission": permission,
    }


def _handler(handlers: Any, key: str) -> Handler:
    if isinstance(handlers, Mapping):
        candidate = handlers.get(key)
    else:
        candidate = getattr(handlers, key, None)
    if not callable(candidate):
        raise DemoError(f"DEMO_HANDLER_MISSING: {key}")
    return candidate


def _dispatch(args: argparse.Namespace, handlers: Any) -> object:
    if args.command == "permission":
        handler = _handler(handlers, "permission")
        return handler(args.action, args.permission_code)
    return _handler(handlers, args.command)()


def _result_dict(result: object) -> dict[str, object]:
    if result is None:
        return {}
    if hasattr(result, "to_dict"):
        result = result.to_dict()  # type: ignore[union-attr]
    elif dataclasses.is_dataclass(result):
        result = dataclasses.asdict(result)
    if isinstance(result, Mapping):
        return dict(result)
    return {"result": result}


def _ensure_status_safe(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if isinstance(key, str) and _FORBIDDEN_STATUS_KEY.search(key):
                raise DemoError("DEMO_STATUS_UNSAFE_OUTPUT")
            _ensure_status_safe(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _ensure_status_safe(nested)


def _success_payload(args: argparse.Namespace, result: object) -> dict[str, object]:
    result_dict = _result_dict(result)
    if _ENVELOPE_KEYS.intersection(result_dict):
        raise DemoError("DEMO_RESERVED_OUTPUT_KEY")
    if args.command == "status":
        _ensure_status_safe(result_dict)
    return {"ok": True, **result_dict}


def main(
    argv: Sequence[str] | None = None,
    handlers: Handlers | object | None = None,
) -> int:
    """Run one allowlisted command and return a deterministic process code.

    ``handlers`` is a test-only injection point at this composition root.  The
    production path resolves the lifecycle handlers lazily after the
    development gate, so command wiring cannot bypass that gate.
    """

    args = parse_args(argv)
    try:
        _ensure_development()
        active_handlers = _default_handlers() if handlers is None else handlers
        result = _dispatch(args, active_handlers)
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print("DEMO_COMMAND_FAILED")
        return 1

    try:
        output = json.dumps(_success_payload(args, result), ensure_ascii=False)
    except DemoError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print("DEMO_COMMAND_FAILED")
        return 1

    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
