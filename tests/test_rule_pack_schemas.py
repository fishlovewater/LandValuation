from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.storage.paths import (
    build_generated_report_object_key,
    build_rule_source_object_key,
)
from app.storage.service import validate_object_key
from app.valuation.rule_packs.schemas import (
    DistrictScope,
    ExistingKnowledgeRulePackCreateRequest,
    FactorLevelInput,
    LandUseType,
    RulePackManifest,
    RulePackSourceManifest,
)


def test_rule_source_and_generated_pdf_use_separate_minio_prefixes() -> None:
    rule_key = build_rule_source_object_key(uuid4(), uuid4(), 1, "官方規則.pdf")
    report_key = build_generated_report_object_key(
        uuid4(), uuid4(), uuid4(), 2, "查估書.pdf"
    )

    assert rule_key.startswith("knowledge/rule-sources/")
    assert "/generated/" in report_key
    assert rule_key != report_key
    assert validate_object_key(rule_key) == rule_key
    assert validate_object_key(report_key) == report_key


def test_manifest_accepts_all_five_land_use_types() -> None:
    manifest = RulePackManifest(
        rule_set_code="NTPC_FACTOR_RULES",
        version_name="使用者提供的正式規則",
        effective_from=date(2026, 8, 27),
        land_use_types=list(LandUseType),
        source_document_type="STANDARD",
        confirm_source_upload=True,
    )

    assert {item.value for item in manifest.land_use_types} == {
        "RESIDENTIAL",
        "COMMERCIAL",
        "INDUSTRIAL",
        "AGRICULTURAL",
        "OTHER",
    }


def test_include_scope_requires_explicit_district_codes() -> None:
    with pytest.raises(ValidationError):
        DistrictScope(mode="INCLUDE", district_codes=[])


def test_include_scope_rejects_non_new_taipei_district_code() -> None:
    with pytest.raises(ValidationError):
        DistrictScope(mode="INCLUDE", district_codes=["123"])

    scope = DistrictScope(mode="INCLUDE", district_codes=["65000270"])
    assert scope.district_codes == ["65000270"]


def test_factor_level_rejects_rate_outside_official_maximum() -> None:
    with pytest.raises(ValidationError):
        FactorLevelInput(
            factor_code="road_width",
            land_use_type="RESIDENTIAL",
            level_code="L1",
            level_name="級距一",
            suggested_rate=Decimal("0.06"),
            maximum_impact_rate=Decimal("0.05"),
            sort_order=1,
        )


def test_supplemental_source_requires_confirmation_and_non_primary_role() -> None:
    with pytest.raises(ValidationError):
        RulePackSourceManifest(
            source_role="PRIMARY",
            source_document_type="STANDARD",
            title="不合法的第二主要來源",
            confirm_source_upload=True,
        )

    with pytest.raises(ValidationError):
        RulePackSourceManifest(
            source_role="LEGAL_BASIS",
            source_document_type="REGULATION",
            title="土地徵收補償市價查估辦法",
            confirm_source_upload=False,
        )


def test_same_rule_version_can_build_distinct_source_object_keys() -> None:
    rule_version_id = uuid4()
    first = build_rule_source_object_key(
        rule_version_id, uuid4(), 2, "評價基準明細表.pdf"
    )
    second = build_rule_source_object_key(
        rule_version_id, uuid4(), 2, "查估作業手冊.pdf"
    )

    assert first != second
    assert first.startswith(f"knowledge/rule-sources/{rule_version_id}/v2/")
    assert second.startswith(f"knowledge/rule-sources/{rule_version_id}/v2/")


def test_manifest_allows_unknown_effective_date_only_for_draft_import() -> None:
    manifest = RulePackManifest(
        rule_set_code="NTPC_PENDING_RULES",
        version_name="等待確認適用日期的規則",
        effective_date_status="UNKNOWN",
        land_use_types=["COMMERCIAL"],
        source_document_type="STANDARD",
        confirm_source_upload=True,
    )

    assert manifest.effective_from is None
    assert manifest.effective_date_status == "UNKNOWN"

    with pytest.raises(ValidationError):
        RulePackManifest(
            rule_set_code="NTPC_BAD_DATE",
            version_name="日期狀態衝突",
            effective_from=date(2026, 8, 27),
            effective_date_status="UNKNOWN",
            land_use_types=["COMMERCIAL"],
            source_document_type="STANDARD",
            confirm_source_upload=True,
        )


def test_existing_knowledge_primary_source_requires_confirmation() -> None:
    with pytest.raises(ValidationError):
        ExistingKnowledgeRulePackCreateRequest(
            source_document_id=uuid4(),
            rule_set_code="NTPC_PENDING_RULES",
            version_name="等待人工確認的規則草稿",
            effective_date_status="UNKNOWN",
            land_use_types=["RESIDENTIAL", "COMMERCIAL"],
            confirm_source_link=False,
        )

    payload = ExistingKnowledgeRulePackCreateRequest(
        source_document_id=uuid4(),
        rule_set_code="NTPC_PENDING_RULES",
        version_name="等待人工確認的規則草稿",
        effective_date_status="UNKNOWN",
        land_use_types=["RESIDENTIAL", "COMMERCIAL"],
        confirm_source_link=True,
    )
    assert payload.effective_from is None


def test_rule_pack_api_does_not_accept_per_district_scope() -> None:
    with pytest.raises(ValidationError):
        RulePackManifest(
            rule_set_code="NTPC_CITYWIDE_ONLY",
            version_name="全新北共用規則",
            effective_date_status="UNKNOWN",
            district_scope={"mode": "INCLUDE", "district_codes": ["65000270"]},
            land_use_types=["COMMERCIAL"],
            source_document_type="STANDARD",
            confirm_source_upload=True,
        )
