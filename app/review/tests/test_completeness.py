from app.review.completeness import (
    CaseInputSnapshot,
    DocumentSnapshot,
    evaluate_completeness,
)


def complete_snapshot():
    return CaseInputSnapshot(
        documents=(
            DocumentSnapshot("original", 1),
            DocumentSnapshot("land-register", 2),
            DocumentSnapshot("cadastral-map", 1),
        ),
        normalized_fields={
            "case_no": "CASE-001",
            "valuation_base_date": "2026-08-25",
            "district_code": "F01",
            "parcel_area": "100.5",
        },
    )


def test_missing_land_register_blocks_core_recalculation():
    snapshot = complete_snapshot()
    snapshot = CaseInputSnapshot(
        documents=tuple(
            item for item in snapshot.documents if item.category != "land-register"
        ),
        normalized_fields=snapshot.normalized_fields,
    )

    result = evaluate_completeness(snapshot)

    assert result.ready is False
    assert result.blocked_rule_codes == {
        "PARCEL_AREA_MATCH",
        "PRICE_RECALCULATION",
    }
    assert result.items[0].document_category == "land-register"


def test_current_document_versions_satisfy_requirements():
    result = evaluate_completeness(complete_snapshot())

    assert result.ready is True
    assert result.items == ()


def test_inactive_document_and_blank_field_do_not_satisfy_requirements():
    snapshot = complete_snapshot()
    snapshot = CaseInputSnapshot(
        documents=snapshot.documents
        + (DocumentSnapshot("original", 2, is_active=False),),
        normalized_fields={**snapshot.normalized_fields, "parcel_area": "  "},
    )

    result = evaluate_completeness(snapshot)

    assert {item.item_code for item in result.items} == {"FIELD_PARCEL_AREA"}
