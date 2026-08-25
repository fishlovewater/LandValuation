from app.review.risks import FindingRisk, risk_level_for_findings


def test_missing_data_remains_processing_state():
    result = risk_level_for_findings([], missing_data=True)

    assert result.level == "MISSING_DATA"


def test_hard_high_categories_override_supplied_low_severity():
    result = risk_level_for_findings(
        [FindingRisk("WRONG_LEGAL_BASIS", "LOW")]
    )

    assert result.level == "HIGH"
    assert result.high_count == 1


def test_expert_judgment_is_at_least_medium_and_resolved_items_are_ignored():
    result = risk_level_for_findings(
        [
            FindingRisk("EXPERT_GRADE_JUDGMENT", "LOW"),
            FindingRisk("PRICE_FORMULA_MISMATCH", "HIGH", resolved=True),
        ]
    )

    assert result.level == "MEDIUM"
    assert result.medium_count == 1
