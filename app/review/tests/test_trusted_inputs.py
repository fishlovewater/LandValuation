import asyncio
from decimal import Decimal
from uuid import uuid4

from app.core.exceptions import AppError
from app.review.repository import ReviewRepository
from app.review.service import ReviewService
from app.review.trusted_inputs import (
    TrustedField,
    prepare_available_rules,
    prepare_trusted_rules,
    required_field_problems,
    trusted_fields_by_code,
    validate_rule_contracts,
)
from app.valuation.submissions.snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    snapshot_fingerprint,
)
import pytest


def field(name="adjustment_rate", *, form_code="F03", value="-12"):
    return TrustedField(
        extracted_field_id="field-1",
        form_code=form_code,
        field_name=name,
        confirmed_value=value,
        source_page=3,
        source_text="來源原文",
        confidence="0.9",
        field_status="APPLIED",
        confirmed_by_user_id="reviewer-1",
        confirmed_at="2026-09-02T00:00:00Z",
    )


def test_applied_confirmed_field_is_available_by_canonical_field_name():
    fields = trusted_fields_by_code([field()])

    assert fields["adjustment_rate"].confirmed_value == "-12"
    assert fields["adjustment_rate"].value_type == "DECIMAL"


def test_missing_canonical_field_is_reported_missing():
    assert required_field_problems({"adjustment_rate"}, {})[0].code == "TRUSTED_INPUT_MISSING"


@pytest.mark.parametrize(
    "ordered_fields",
    [
        [field(), field()],
        [field(), field(form_code="F04")],
    ],
)
def test_duplicate_applied_fields_are_not_trusted_in_either_form(ordered_fields):
    fields = trusted_fields_by_code(ordered_fields)

    assert required_field_problems({"adjustment_rate"}, fields)[0].code == "TRUSTED_INPUT_MISSING"


def test_float_confirmed_value_is_not_a_trusted_decimal():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate": "0.3", "tolerance": "0.1"}',
            }
        ]
    )

    with pytest.raises(AppError) as raised:
        prepare_trusted_rules(contracts, {"adjustment_rate": field(value=0.1 + 0.2)})

    assert raised.value.code == "TRUSTED_INPUT_UNVERIFIED"


def test_available_rules_skip_only_checks_whose_ocr_fields_are_missing():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate":"-5","tolerance":"0"}',
            },
            {
                "rule_code": "EXPERT_GRADE",
                "target_field_code": "expert_grade",
                "rule_expression": '{"system_grade":"A"}',
            },
        ]
    )

    prepared, skipped = prepare_available_rules(
        contracts,
        {"expert_grade": field("expert_grade", value="A")},
    )

    assert [item.rule["rule_code"] for item in prepared] == ["EXPERT_GRADE"]
    assert [item.rule["rule_code"] for item in skipped] == ["ADJUSTMENT_RATE"]
    assert skipped[0].reason_code == "INPUT_UNAVAILABLE"
    assert skipped[0].missing_field_codes == ("adjustment_rate",)


def test_available_rules_skip_unusable_ocr_value_instead_of_failing_whole_run():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate":"-5","tolerance":"0"}',
            }
        ]
    )

    prepared, skipped = prepare_available_rules(
        contracts,
        {"adjustment_rate": field(value=0.1 + 0.2)},
    )

    assert prepared == ()
    assert skipped[0].reason_code == "INPUT_UNVERIFIED"
    assert skipped[0].missing_field_codes == ("adjustment_rate",)


def test_rule_json_numbers_are_parsed_as_exact_decimals():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "ADJUSTMENT_RATE",
                "target_field_code": "adjustment_rate",
                "rule_expression": '{"system_rate": 0.1, "tolerance": 0.2}',
            }
        ]
    )

    contract = contracts[0]
    assert contract.system_rate == Decimal("0.1")
    assert contract.tolerance == Decimal("0.2")
    assert contract.configuration == {
        "system_rate": Decimal("0.1"),
        "tolerance": Decimal("0.2"),
    }


def test_f03_weight_sum_contract_requires_both_canonical_weight_fields():
    contract = validate_rule_contracts(
        [
            {
                "rule_code": "F03_WEIGHT_SUM",
                "target_field_code": "comparison_weight,income_weight",
                "rule_expression": '{"expected_total":"1","tolerance":"0.000001"}',
            }
        ]
    )[0]

    assert contract.required_field_codes == ("comparison_weight", "income_weight")
    assert contract.expected_total == Decimal("1")
    assert contract.tolerance == Decimal("0.000001")


def test_f03_weight_sum_contract_rejects_noncanonical_target_fields():
    with pytest.raises(AppError) as raised:
        validate_rule_contracts(
            [
                {
                    "rule_code": "F03_WEIGHT_SUM",
                    "target_field_code": "income_weight,comparison_weight",
                    "rule_expression": '{"expected_total":"1","tolerance":"0.000001"}',
                }
            ]
        )

    assert raised.value.code == "RULE_CONFIGURATION_INVALID"


def test_f03_weight_sum_preflight_uses_exact_confirmed_decimals():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "F03_WEIGHT_SUM",
                "target_field_code": "comparison_weight,income_weight",
                "rule_expression": '{"expected_total":"1","tolerance":"0.000001"}',
            }
        ]
    )
    fields = {
        "comparison_weight": field("comparison_weight", value="0.6"),
        "income_weight": field("income_weight", value="0.4"),
    }

    prepared = prepare_trusted_rules(contracts, fields)[0]

    assert tuple(item.field_code for item in prepared.source_fields) == (
        "comparison_weight",
        "income_weight",
    )
    assert prepared.weight_sum_result is not None
    assert prepared.weight_sum_result.total == Decimal("1.0")
    assert prepared.weight_sum_result.valid is True


def test_f03_weight_sum_preflight_rejects_float_confirmed_weight():
    contracts = validate_rule_contracts(
        [
            {
                "rule_code": "F03_WEIGHT_SUM",
                "target_field_code": "comparison_weight,income_weight",
                "rule_expression": '{"expected_total":"1","tolerance":"0.000001"}',
            }
        ]
    )
    fields = {
        "comparison_weight": field("comparison_weight", value=0.6),
        "income_weight": field("income_weight", value="0.4"),
    }

    with pytest.raises(AppError) as raised:
        prepare_trusted_rules(contracts, fields)

    assert raised.value.code == "TRUSTED_INPUT_UNVERIFIED"


class _MappingsResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self.rows


class _RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.parameters = None

    async def execute(self, statement, parameters):
        self.statement = str(statement)
        self.parameters = parameters
        return _MappingsResult(self.rows)


def test_repository_reads_only_applied_confirmed_canonical_fields():
    case_id = uuid4()
    session = _RecordingSession(
        [
            {
                "extracted_field_id": uuid4(),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12",
                "source_page": 3,
                "source_text": "來源原文",
                "confidence": "0.9",
                "field_status": "APPLIED",
                "confirmed_by_user_id": uuid4(),
                "confirmed_at": "2026-09-02T00:00:00Z",
            }
        ]
    )

    rows = asyncio.run(
        ReviewRepository(session).list_applied_confirmed_extracted_fields(case_id)
    )

    assert rows[0]["field_name"] == "adjustment_rate"
    assert session.parameters == {"case_id": case_id}
    assert "ef.field_status = 'APPLIED'" in session.statement
    assert "ef.confirmed_value IS NOT NULL" in session.statement
    assert "JOIN valuation.documents AS d" in session.statement
    assert "d.document_type = 'original'" in session.statement
    assert "d.is_active = true" in session.statement
    assert "valuation.document_extractions" in session.statement
    assert "extraction_status = 'COMPLETED'" in session.statement
    assert "extraction_run_id" not in session.statement
    assert "field_code" not in session.statement
    assert "normalized_value" not in session.statement


def test_service_maps_canonical_applied_field_to_trusted_field():
    trusted = ReviewService._trusted_field(
        {
            "extracted_field_id": uuid4(),
            "form_code": "F03",
            "field_name": "adjustment_rate",
            "confirmed_value": "-12",
            "source_page": 3,
            "source_text": "來源原文",
            "confidence": "0.9",
            "field_status": "APPLIED",
            "confirmed_by_user_id": uuid4(),
            "confirmed_at": "2026-09-02T00:00:00Z",
        }
    )

    assert trusted.field_name == "adjustment_rate"
    assert trusted.confirmed_value == "-12"
    assert trusted.source_page == 3


def _valid_submission_snapshot():
    document_id = uuid4()
    field_id = uuid4()
    submitted_by = uuid4()
    request_id = uuid4()
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "case_version": 3,
        "submitted_by_user_id": str(submitted_by),
        "request_id": str(request_id),
        "applied_fields": [
            {
                "extracted_field_id": str(field_id),
                "document_id": str(document_id),
                "form_code": "F03",
                "field_name": "adjustment_rate",
                "confirmed_value": "-12.0000",
                "source_page": 3,
                "source_text": "調整率 -12%",
                "confidence": "0.9500",
                "field_status": "APPLIED",
                "confirmed_by_user_id": str(submitted_by),
                "confirmed_at": "2026-09-03T12:34:56+00:00",
            }
        ],
        "calculations": {},
        "documents": [
            {
                "document_id": str(document_id),
                "document_type": "original",
                "original_filename": "source.pdf",
                "mime_type": "application/pdf",
                "version_no": 1,
                "document_group_id": str(uuid4()),
                "checksum_sha256": "a" * 64,
                "file_size_bytes": 100,
                "uploaded_at": "2026-09-03T12:00:00+00:00",
                "is_active": True,
            }
        ],
        "validation": {},
    }


@pytest.mark.parametrize(
    "missing_key",
    [
        "schema_version",
        "case_version",
        "submitted_by_user_id",
        "request_id",
        "applied_fields",
        "calculations",
        "documents",
        "validation",
    ],
)
def test_submission_snapshot_requires_every_top_level_key(missing_key):
    snapshot = _valid_submission_snapshot()
    del snapshot[missing_key]

    with pytest.raises(AppError) as raised:
        ReviewService._snapshot_trusted_inputs(snapshot)

    assert raised.value.code == "SUBMISSION_SNAPSHOT_INVALID"
    assert raised.value.status_code == 409


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("case_version",), True),
        (("submitted_by_user_id",), "not-a-uuid"),
        (("request_id",), "not-a-uuid"),
        (("applied_fields", 0, "extracted_field_id"), 17),
        (("applied_fields", 0, "document_id"), "not-a-uuid"),
        (("applied_fields", 0, "form_code"), 17),
        (("applied_fields", 0, "field_name"), 17),
        (("applied_fields", 0, "confirmed_value"), None),
        (("applied_fields", 0, "source_page"), "3"),
        (("applied_fields", 0, "source_text"), 3),
        (("applied_fields", 0, "confidence"), 0.95),
        (("applied_fields", 0, "field_status"), "CONFIRMED"),
        (("applied_fields", 0, "confirmed_by_user_id"), "not-a-uuid"),
        (("applied_fields", 0, "confirmed_at"), "not-a-timestamp"),
        (("documents", 0, "document_id"), "not-a-uuid"),
        (("documents", 0, "document_type"), 17),
        (("documents", 0, "version_no"), "1"),
        (("documents", 0, "document_group_id"), "not-a-uuid"),
        (("documents", 0, "checksum_sha256"), "bad-checksum"),
        (("documents", 0, "file_size_bytes"), -1),
        (("documents", 0, "uploaded_at"), "not-a-timestamp"),
        (("documents", 0, "is_active"), "true"),
    ],
)
def test_submission_snapshot_rejects_malformed_values(path, value):
    snapshot = _valid_submission_snapshot()
    target = snapshot
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(AppError) as raised:
        ReviewService._snapshot_trusted_inputs(snapshot)

    assert raised.value.code == "SUBMISSION_SNAPSHOT_INVALID"
    assert raised.value.status_code == 409


def test_submission_snapshot_requires_field_evidence_keys():
    snapshot = _valid_submission_snapshot()
    del snapshot["applied_fields"][0]["source_page"]
    del snapshot["applied_fields"][0]["source_text"]

    with pytest.raises(AppError) as raised:
        ReviewService._snapshot_trusted_inputs(snapshot)

    assert raised.value.code == "SUBMISSION_SNAPSHOT_INVALID"


def test_submission_snapshot_rejects_mismatched_input_fingerprint():
    snapshot = _valid_submission_snapshot()

    with pytest.raises(AppError) as raised:
        ReviewService._snapshot_trusted_inputs(
            snapshot, input_fingerprint="0" * 64
        )

    assert raised.value.code == "SUBMISSION_SNAPSHOT_INVALID"


def test_submission_snapshot_accepts_its_canonical_input_fingerprint():
    snapshot = _valid_submission_snapshot()

    document, fields = ReviewService._snapshot_trusted_inputs(
        snapshot, input_fingerprint=snapshot_fingerprint(snapshot)
    )

    assert document["document_id"] == snapshot["documents"][0]["document_id"]
    assert fields[0].document_id == snapshot["applied_fields"][0]["document_id"]
