from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.valuation.official_field_catalog import OFFICIAL_PDF_FIELDS
from app.valuation.report_packages.official_template_overlay import (
    build_template_manifest_skeleton,
    validate_template_manifest,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "建立或驗證官方空白 PDF 的 overlay manifest。"
            " skeleton 只建立模板身份與待校準欄位，不會猜座標。"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    skeleton = subparsers.add_parser("skeleton", help="建立待校準 manifest")
    skeleton.add_argument("--pdf", required=True, type=Path)
    skeleton.add_argument("--output", required=True, type=Path)
    skeleton.add_argument("--template-name", required=True)
    skeleton.add_argument(
        "--form",
        choices=sorted(OFFICIAL_PDF_FIELDS),
        help="使用既有 F01/F02/F03/F04 官方 PDF 欄位清單",
    )
    skeleton.add_argument(
        "--field-code",
        action="append",
        default=[],
        help="額外指定欄位，可重複使用；完整查估書 package 可用這個模式",
    )

    validate = subparsers.add_parser("validate", help="驗證已校準 manifest")
    validate.add_argument("--pdf", required=True, type=Path)
    validate.add_argument("--manifest", required=True, type=Path)
    validate.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="只檢查模板身份、頁面與已填座標；允許 unmapped_fields 尚未清空",
    )
    return parser


def _read_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise SystemExit(f"找不到檔案：{path}")
    return path.read_bytes()


def _skeleton(args: argparse.Namespace) -> None:
    fields = list(args.field_code)
    if args.form:
        fields.extend(field.code for field in OFFICIAL_PDF_FIELDS[args.form])
    if not fields:
        raise SystemExit("至少要提供 --form 或一個 --field-code")
    manifest = build_template_manifest_skeleton(
        _read_bytes(args.pdf),
        fields,
        template_name=args.template_name,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已建立 manifest skeleton：{args.output}")
    print(f"待校準欄位：{len(manifest['unmapped_fields'])}")
    print(f"模板 SHA-256：{manifest['template_sha256']}")


def _validate(args: argparse.Namespace) -> None:
    if not args.manifest.is_file():
        raise SystemExit(f"找不到 manifest：{args.manifest}")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    validated = validate_template_manifest(
        _read_bytes(args.pdf),
        manifest,
        require_complete=not args.allow_incomplete,
    )
    print("manifest 驗證通過")
    print(f"頁數：{len(validated['pages'])}")
    print(f"已校準座標：{len(validated['placements'])}")
    print(f"尚未校準：{len(validated.get('unmapped_fields') or [])}")


def main() -> None:
    args = _parser().parse_args()
    if args.command == "skeleton":
        _skeleton(args)
        return
    _validate(args)


if __name__ == "__main__":
    main()