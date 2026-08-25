from dataclasses import dataclass


HIGH_IMPACT_FIELD_CODES = frozenset(
    {
        "adjustment_rate",
        "comparison_price",
        "recalculated_price",
        "final_valuation",
        "expert_grade",
        "legal_basis",
    }
)


@dataclass(frozen=True)
class TrustedField:
    extracted_field_id: str
    field_code: str
    field_path: str
    raw_text: str
    normalized_value: object
    value_type: str
    page_number: int
    verification_status: str
    is_official: bool


@dataclass(frozen=True)
class TrustedInputProblem:
    code: str
    field_code: str


@dataclass(frozen=True)
class TrustedRunContext:
    document: dict
    extraction_run: dict
    fields: dict[str, TrustedField]
    rule_version: dict
    validation_rules: tuple[dict, ...]
    rule_source: dict


def trusted_fields_by_code(fields):
    official_counts = {}
    official_fields = {}
    for item in fields:
        if item.is_official:
            official_counts[item.field_code] = official_counts.get(item.field_code, 0) + 1
            official_fields[item.field_code] = item
    return {
        code: item
        for code, item in official_fields.items()
        if official_counts[code] == 1
    }


def required_field_problems(required_codes, fields):
    problems = []
    for code in sorted(required_codes):
        item = fields.get(code)
        if item is None or item.verification_status == "REJECTED":
            problems.append(TrustedInputProblem("TRUSTED_INPUT_MISSING", code))
        elif (
            code in HIGH_IMPACT_FIELD_CODES
            and item.verification_status != "VERIFIED"
        ):
            problems.append(TrustedInputProblem("TRUSTED_INPUT_UNVERIFIED", code))
        elif item.verification_status not in {"AUTO_EXTRACTED", "VERIFIED"}:
            problems.append(TrustedInputProblem("TRUSTED_INPUT_UNVERIFIED", code))
    return tuple(problems)
