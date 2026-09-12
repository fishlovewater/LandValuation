from datetime import UTC, datetime
from uuid import uuid4

from app.review.reports import (
    ReportCase,
    ReportCoverage,
    ReportDecision,
    ReportInputDocument,
    ReportInputProvenance,
    ReportRiskSummary,
    ReportRun,
    ReportSkippedRule,
    ReviewReportInput,
    build_review_report,
)


def report_input():
    finding_id = uuid4()
    document_id = uuid4()
    return ReviewReportInput(
        case=ReportCase(
            case_id=uuid4(),
            case_no="CASE-REPORT-001",
            case_title="報告測試案件",
            valuation_base_date="2026-08-25",
            district_code="F01",
        ),
        run=ReportRun(
            validation_run_id=uuid4(),
            run_no=2,
            run_status="COMPLETED",
            rule_version_id=uuid4(),
            model_id="model-v1",
            prompt_version="prompt-v1",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        ),
        review_status="REVIEW_REQUIRED",
        missing_item_count=0,
        findings=[
            {
                "finding_id": finding_id,
                "finding_code": "RATE-001",
                "finding_type": "RATE_OUT_OF_RANGE",
                "severity": "HIGH",
                "title": "調整率不一致",
                "description": "報告值與重算值不同",
                "status": "PARTIALLY_ACCEPTED",
                "source_evidence": [
                    {
                        "source_id": "report-p3",
                        "extracted_field_id": "field-v1",
                        "document_id": "document-v1",
                        "document_version": 1,
                        "page": 3,
                        "field_path": "comparables[0].adjustment_rate",
                        "excerpt": "Adjustment rate -12%",
                        "verification_status": "VERIFIED",
                    }
                ],
                "reported_text": "-12%",
                "reported_value": "-12",
                "legal_basis": [{"source_id": "law-a10", "article": "第10條"}],
                "reported_adjustment_rate": "-12.000000",
                "system_adjustment_rate": "-5.000000",
                "comparison_result": {"difference": "-7.00"},
                "recommended_action": {"action": "VERIFY"},
                "ai_status": "AVAILABLE",
                "ai_reasoning_summary": "報告值與正式重算結果不一致。",
                "ai_confidence": "0.9000",
            }
        ],
        risk_summary=ReportRiskSummary(
            overall_risk_level="HIGH",
            high_count=1,
            medium_count=0,
            low_count=0,
            missing_item_count=0,
            risk_reasons=["RATE_OUT_OF_RANGE"],
        ),
        review_coverage=ReportCoverage(
            total_rule_count=2,
            executed_rule_count=1,
            skipped_rule_count=1,
            skipped_rules=[
                ReportSkippedRule(
                    validation_rule_id=uuid4(),
                    rule_code="LAND_REGISTER_CROSSCHECK",
                    rule_name="土地登記資料交叉檢核",
                    reason_code="MISSING_REQUIRED_FIELDS",
                    reason="缺少可供交叉檢核的土地登記資料",
                    missing_field_codes=["LAND_REGISTER_AREA"],
                )
            ],
        ),
        decisions=[
            ReportDecision(
                decision_id=uuid4(),
                finding_id=finding_id,
                decision="PARTIALLY_ACCEPTED",
                reason="現勘資料支持部分調整",
                decided_by_user_id=uuid4(),
                decided_at=datetime.now(UTC),
                after_value={"reported_rate": "-7.00"},
            )
        ],
        input_provenance=ReportInputProvenance(
            source="EXTERNAL",
            version_no=2,
            frozen_at=datetime(2026, 9, 12, 8, 0, tzinfo=UTC),
            fingerprint="a" * 64,
            schema_version="external-review-input-v1",
            external_input_snapshot_id=uuid4(),
            documents=[
                ReportInputDocument(
                    document_id=document_id,
                    document_group_id=uuid4(),
                    document_type="original",
                    version_no=2,
                    checksum_sha256="b" * 64,
                    original_filename="external-report-v2.pdf",
                )
            ],
        ),
    )


def test_report_keeps_machine_ai_and_human_records_separate():
    data = report_input()

    report = build_review_report(data)

    assert report.run.validation_run_id == data.run.validation_run_id
    assert report.findings[0].source_evidence
    assert report.findings[0].source_evidence[0]["extracted_field_id"] == "field-v1"
    assert report.findings[0].source_evidence[0]["verification_status"] == "VERIFIED"
    assert report.findings[0].ai_assessment.reasoning_summary
    assert report.findings[0].decisions[0].reason == "現勘資料支持部分調整"
    assert report.risk_summary.high_count == 1
    assert report.review_coverage is not None
    assert report.review_coverage.executed_rule_count == 1
    assert report.review_coverage.skipped_rule_count == 1
    assert report.review_coverage.skipped_rules[0].status == "SKIPPED"
    assert report.input_provenance is not None
    assert report.input_provenance.source == "EXTERNAL"
    assert report.input_provenance.version_no == 2
    assert report.input_provenance.documents[0].original_filename == "external-report-v2.pdf"


def test_report_does_not_expose_storage_endpoints_or_hidden_reasoning():
    serialized = build_review_report(report_input()).model_dump_json()

    assert "localhost" not in serialized
    assert "presigned" not in serialized
    assert "chain_of_thought" not in serialized
    assert "object_key" not in serialized
