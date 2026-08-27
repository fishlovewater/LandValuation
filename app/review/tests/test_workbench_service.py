from uuid import uuid4

from app.review.workbench_service import WorkbenchService


def test_version_diffs_compare_only_within_document_lineage():
    group_a = uuid4()
    group_b = uuid4()
    rows = [
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-12",
            "raw_text": "-12%",
            "page_number": 3,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 2,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-7",
            "raw_text": "-7%",
            "page_number": 3,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_b,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": "comparables[0].adjustment_rate",
            "normalized_value": "-20",
            "raw_text": "-20%",
            "page_number": 8,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 1,
            "field_code": "adjustment_rate",
            "field_path": None,
            "normalized_value": "-15",
            "raw_text": "-15%",
            "page_number": 9,
        },
        {
            "document_id": uuid4(),
            "document_group_id": group_a,
            "document_version": 2,
            "field_code": "adjustment_rate",
            "field_path": None,
            "normalized_value": "-10",
            "raw_text": "-10%",
            "page_number": 9,
        },
    ]

    result = WorkbenchService._version_diffs(rows)

    assert len(result) == 2
    assert {item.document_group_id for item in result} == {group_a}
    by_path = {item.field_path: item for item in result}
    assert by_path["comparables[0].adjustment_rate"].previous.normalized_value == "-12"
    assert by_path["comparables[0].adjustment_rate"].current.normalized_value == "-7"
    assert by_path[None].previous.normalized_value == "-15"
    assert by_path[None].current.normalized_value == "-10"
