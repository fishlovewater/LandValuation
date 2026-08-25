from dataclasses import dataclass
from typing import Any, Literal, Sequence

from app.review.trusted_inputs import TrustedInputProblem


@dataclass(frozen=True)
class DocumentSnapshot:
    category: str
    version: int
    is_active: bool = True


@dataclass(frozen=True)
class CaseInputSnapshot:
    documents: tuple[DocumentSnapshot, ...]
    normalized_fields: dict[str, Any]


@dataclass(frozen=True)
class Requirement:
    code: str
    name: str
    kind: Literal["document", "field"]
    target: str
    blocked_rule_codes: frozenset[str]


@dataclass(frozen=True)
class MissingRequirement:
    item_code: str
    item_name: str
    document_category: str | None
    field_path: str | None
    blocked_rule_codes: frozenset[str]


@dataclass(frozen=True)
class CompletenessResult:
    ready: bool
    items: tuple[MissingRequirement, ...]
    blocked_rule_codes: frozenset[str]


MVP_REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        "DOC_ORIGINAL",
        "估價報告原始文件",
        "document",
        "original",
        frozenset({"SOURCE_DOCUMENT_REQUIRED"}),
    ),
    Requirement(
        "DOC_LAND_REGISTER",
        "土地登記謄本",
        "document",
        "land-register",
        frozenset({"PARCEL_AREA_MATCH", "PRICE_RECALCULATION"}),
    ),
    Requirement(
        "DOC_CADASTRAL_MAP",
        "地籍圖",
        "document",
        "cadastral-map",
        frozenset({"PARCEL_LOCATION_MATCH"}),
    ),
    Requirement(
        "FIELD_CASE_NO",
        "案件編號",
        "field",
        "case_no",
        frozenset({"CASE_IDENTITY"}),
    ),
    Requirement(
        "FIELD_VALUATION_BASE_DATE",
        "估價基準日",
        "field",
        "valuation_base_date",
        frozenset({"RULE_EFFECTIVITY"}),
    ),
    Requirement(
        "FIELD_DISTRICT_CODE",
        "行政區代碼",
        "field",
        "district_code",
        frozenset({"DISTRICT_RULE"}),
    ),
    Requirement(
        "FIELD_PARCEL_AREA",
        "宗地面積",
        "field",
        "parcel_area",
        frozenset({"PARCEL_AREA_MATCH", "PRICE_RECALCULATION"}),
    ),
)


def evaluate_completeness(
    snapshot: CaseInputSnapshot,
    requirements: Sequence[Requirement] = MVP_REQUIREMENTS,
) -> CompletenessResult:
    active_latest: dict[str, DocumentSnapshot] = {}
    for document in snapshot.documents:
        if not document.is_active:
            continue
        current = active_latest.get(document.category)
        if current is None or document.version > current.version:
            active_latest[document.category] = document

    missing: list[MissingRequirement] = []
    for requirement in requirements:
        if requirement.kind == "document":
            present = requirement.target in active_latest
        else:
            value = snapshot.normalized_fields.get(requirement.target)
            present = value is not None and (
                not isinstance(value, str) or bool(value.strip())
            )
        if present:
            continue
        missing.append(
            MissingRequirement(
                item_code=requirement.code,
                item_name=requirement.name,
                document_category=(
                    requirement.target if requirement.kind == "document" else None
                ),
                field_path=(
                    requirement.target if requirement.kind == "field" else None
                ),
                blocked_rule_codes=requirement.blocked_rule_codes,
            )
        )

    blocked = frozenset(
        code for item in missing for code in item.blocked_rule_codes
    )
    return CompletenessResult(not missing, tuple(missing), blocked)


def trusted_problem_to_missing(
    problem: TrustedInputProblem,
) -> MissingRequirement:
    suffix = problem.field_code.upper()
    return MissingRequirement(
        item_code=f"{problem.code}_{suffix}",
        item_name=f"正式檢核欄位：{problem.field_code}",
        document_category="original",
        field_path=problem.field_code,
        blocked_rule_codes=frozenset({"TRUSTED_INPUT_REQUIRED"}),
    )


def trusted_context_missing_requirement() -> MissingRequirement:
    return MissingRequirement(
        item_code="TRUSTED_INPUT_MISSING",
        item_name="正式檢核資料尚未完成",
        document_category="original",
        field_path=None,
        blocked_rule_codes=frozenset({"TRUSTED_INPUT_REQUIRED"}),
    )
