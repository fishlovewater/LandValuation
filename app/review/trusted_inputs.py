import json
from dataclasses import dataclass
from decimal import Decimal, DecimalException, InvalidOperation

from app.core.exceptions import AppError
from app.review.recalculation import AdjustmentResult, RATE_QUANTUM, recalculate_adjustment_rate


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
    bounding_box: object
    confidence: object | None
    verification_status: str
    verified_by_user_id: str | None
    verified_at: object | None
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
    official_fields: tuple[TrustedField, ...]
    rule_version: dict
    validation_rules: tuple[dict, ...]
    rule_source: dict
    prepared_rules: tuple["PreparedRule", ...]


@dataclass(frozen=True)
class PreparedRule:
    rule: dict
    field: TrustedField
    configuration: dict
    reported_rate: Decimal | None = None
    system_rate: Decimal | None = None
    tolerance: Decimal | None = None
    adjustment_result: AdjustmentResult | None = None
    reported_grade: str | None = None
    system_grade: str | None = None


@dataclass(frozen=True)
class RuleContract:
    rule: dict
    target_field_code: str
    expected_value_type: str
    configuration: dict
    system_rate: Decimal | None = None
    tolerance: Decimal | None = None
    system_grade: str | None = None


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


def _configuration_error(message: str, rule: dict) -> AppError:
    return AppError(
        "RULE_CONFIGURATION_INVALID",
        message,
        409,
        {"rule_code": rule.get("rule_code")},
    )


def _unverified_value_error(field: TrustedField) -> AppError:
    return AppError(
        "TRUSTED_INPUT_UNVERIFIED",
        f"正式抽取欄位格式無法用於檢核：{field.field_code}",
        409,
        {"field_code": field.field_code},
    )


def _finite_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        return None
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal_value if decimal_value.is_finite() else None


def validate_rule_contracts(validation_rules) -> tuple[RuleContract, ...]:
    contracts = []
    expected_fields = {
        "ADJUSTMENT_RATE": ("adjustment_rate", "DECIMAL"),
        "EXPERT_GRADE": ("expert_grade", "TEXT"),
    }
    for rule in validation_rules:
        rule_code = rule.get("rule_code")
        target_field_code = rule.get("target_field_code")
        if rule_code not in expected_fields:
            raise _configuration_error(f"尚未支援規則：{rule_code}", rule)
        if not isinstance(target_field_code, str) or not target_field_code.strip():
            raise _configuration_error("檢核規則缺少 target_field_code", rule)
        expected_field_code, expected_value_type = expected_fields[rule_code]
        if target_field_code != expected_field_code:
            raise _configuration_error(
                f"規則 {rule_code} 的 target_field_code 不正確", rule
            )
        try:
            configuration = json.loads(rule["rule_expression"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _configuration_error("正式規則設定不是有效 JSON", rule) from exc
        if not isinstance(configuration, dict):
            raise _configuration_error("正式規則設定必須是 JSON object", rule)

        if rule_code == "ADJUSTMENT_RATE":
            system_rate = _finite_decimal(configuration.get("system_rate"))
            tolerance = _finite_decimal(configuration.get("tolerance"))
            if system_rate is None or tolerance is None:
                raise _configuration_error(
                    "調整率規則缺少有效的 system_rate 或 tolerance", rule
                )
            if tolerance < 0:
                raise _configuration_error("調整率規則 tolerance 不得為負值", rule)
            try:
                tolerance.quantize(RATE_QUANTUM)
                recalculate_adjustment_rate(Decimal("0"), system_rate, tolerance)
            except (DecimalException, OverflowError) as exc:
                raise _configuration_error(
                    "調整率規則的數值無法執行計算", rule
                ) from exc
            contracts.append(
                RuleContract(
                    rule=rule,
                    target_field_code=target_field_code,
                    expected_value_type=expected_value_type,
                    configuration=configuration,
                    system_rate=system_rate,
                    tolerance=tolerance,
                )
            )
        else:
            system_grade = configuration.get("system_grade")
            if not isinstance(system_grade, str) or not system_grade.strip():
                raise _configuration_error("級距規則缺少有效的 system_grade", rule)
            contracts.append(
                RuleContract(
                    rule=rule,
                    target_field_code=target_field_code,
                    expected_value_type=expected_value_type,
                    configuration=configuration,
                    system_grade=system_grade,
                )
            )
    return tuple(contracts)


def prepare_trusted_rules(
    contracts: tuple[RuleContract, ...], fields: dict[str, TrustedField]
) -> tuple[PreparedRule, ...]:
    prepared = []
    for contract in contracts:
        field = fields.get(contract.target_field_code)
        if field is None:
            raise AppError(
                "TRUSTED_INPUT_UNVERIFIED",
                f"正式抽取欄位不可用：{contract.target_field_code}",
                409,
                {"field_code": contract.target_field_code},
            )
        if field.value_type != contract.expected_value_type:
            raise _unverified_value_error(field)
        if contract.rule["rule_code"] == "ADJUSTMENT_RATE":
            reported_rate = _finite_decimal(field.normalized_value)
            if reported_rate is None:
                raise _unverified_value_error(field)
            try:
                adjustment_result = recalculate_adjustment_rate(
                    reported_rate, contract.system_rate, contract.tolerance
                )
            except (DecimalException, OverflowError) as exc:
                raise _unverified_value_error(field) from exc
            prepared.append(
                PreparedRule(
                    rule=contract.rule,
                    field=field,
                    configuration=contract.configuration,
                    reported_rate=reported_rate,
                    system_rate=contract.system_rate,
                    tolerance=contract.tolerance,
                    adjustment_result=adjustment_result,
                )
            )
        else:
            if not isinstance(field.normalized_value, str) or not field.normalized_value.strip():
                raise _unverified_value_error(field)
            prepared.append(
                PreparedRule(
                    rule=contract.rule,
                    field=field,
                    configuration=contract.configuration,
                    reported_grade=field.normalized_value,
                    system_grade=contract.system_grade,
                )
            )
    return tuple(prepared)
