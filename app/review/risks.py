from dataclasses import dataclass


@dataclass(frozen=True)
class FindingRisk:
    finding_type: str
    severity: str
    resolved: bool = False


@dataclass(frozen=True)
class RiskResult:
    level: str
    high_count: int
    medium_count: int
    low_count: int


def risk_level_for_findings(findings, missing_data: bool = False) -> RiskResult:
    if missing_data:
        return RiskResult("MISSING_DATA", 0, 0, 0)

    high_types = {
        "WRONG_LEGAL_BASIS",
        "OPPOSITE_DIRECTION",
        "RATE_OUT_OF_RANGE",
        "PRICE_FORMULA_MISMATCH",
        "CRITICAL_SOURCE_CONTRADICTION",
    }
    severity_rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    normalized: list[str] = []
    for finding in findings:
        if finding.resolved:
            continue
        severity = finding.severity
        if finding.finding_type in high_types and severity_rank.get(severity, 0) < 3:
            severity = "HIGH"
        if (
            finding.finding_type == "EXPERT_GRADE_JUDGMENT"
            and severity_rank.get(severity, 0) < 2
        ):
            severity = "MEDIUM"
        normalized.append(severity)

    if not normalized:
        return RiskResult("LOW", 0, 0, 0)
    level = max(normalized, key=lambda value: severity_rank.get(value, 0))
    return RiskResult(
        level=level,
        high_count=sum(value in {"HIGH", "CRITICAL"} for value in normalized),
        medium_count=normalized.count("MEDIUM"),
        low_count=normalized.count("LOW"),
    )
