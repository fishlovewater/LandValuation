"""Pure behavior tests for correction snapshot building and gates."""

from app.review.corrections import build_correction_item_snapshot


class _Finding:
    def __init__(self, **values):
        self.__dict__.update(values)


def _finding(**overrides):
    base = dict(
        finding_id="11111111-1111-1111-1111-111111111111",
        finding_code="RULE:field",
        finding_type="RATE_OUT_OF_RANGE",
        severity="HIGH",
        document_id="22222222-2222-2222-2222-222222222222",
        document_version=1,
        page_number=3,
        reported_text="調整率 -12%",
        reported_value="-12",
        legal_basis=[{"rule_code": "ADJUSTMENT_RATE"}],
        source_evidence=[{"extracted_field_id": "f1"}],
        title="調整率超出允許差異",
        description="需人工核對",
    )
    base.update(overrides)
    return _Finding(**base)


def test_snapshot_copies_finding_evidence_and_legal_basis():
    snapshot = build_correction_item_snapshot(_finding())
    assert snapshot["finding_code"] == "RULE:field"
    assert snapshot["finding_type"] == "RATE_OUT_OF_RANGE"
    assert snapshot["severity"] == "HIGH"
    assert snapshot["page_number"] == 3
    assert snapshot["reported_value"] == "-12"
    assert snapshot["legal_basis_snapshot"] == [{"rule_code": "ADJUSTMENT_RATE"}]
    assert snapshot["source_evidence_snapshot"] == [{"extracted_field_id": "f1"}]
    assert snapshot["issue_summary"]
    assert snapshot["requested_correction"]


def test_snapshot_never_contains_formal_value_or_selection_source():
    snapshot = build_correction_item_snapshot(_finding())
    assert "after_value" not in snapshot
    assert "selection_source" not in snapshot
    assert "value" not in snapshot
