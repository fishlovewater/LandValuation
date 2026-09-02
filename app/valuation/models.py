from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, add_mapped_attribute, mapped_column

from app.db.base import Base
# Review owns the shared table declarations.  Extend those single mappings
# instead of declaring the same SQLAlchemy tables twice when the 0010 schema
# introduces the Operations request-correlation fields.
from app.review.models import ValidationFinding as ValidationFindingRecord
from app.review.models import ValidationRun as ValidationRunRecord


add_mapped_attribute(
    ValidationRunRecord,
    "request_id",
    mapped_column(PGUUID(as_uuid=True)),
)
add_mapped_attribute(
    ValidationFindingRecord,
    "request_id",
    mapped_column(PGUUID(as_uuid=True)),
)
add_mapped_attribute(
    ValidationFindingRecord,
    "created_at",
    mapped_column(DateTime(timezone=True), server_default=func.now()),
)


class CaseRecord(Base):
    __tablename__ = "cases"
    __table_args__ = {"schema": "valuation"}

    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_no: Mapped[str] = mapped_column(String(50), unique=True)
    case_title: Mapped[str] = mapped_column(String(200))
    case_type: Mapped[str] = mapped_column(String(50))
    requesting_agency: Mapped[str | None] = mapped_column(String(200))
    valuation_base_date: Mapped[date] = mapped_column(Date)
    city_code: Mapped[str] = mapped_column(String(20))
    district_code: Mapped[str] = mapped_column(String(20))
    land_use_type: Mapped[str | None] = mapped_column(String(100))
    case_status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    created_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ParcelRecord(Base):
    __tablename__ = "parcels"
    __table_args__ = {"schema": "valuation"}

    parcel_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("valuation.cases.case_id")
    )
    district_code: Mapped[str] = mapped_column(String(20))
    section_name: Mapped[str] = mapped_column(String(100))
    subsection_name: Mapped[str] = mapped_column(String(100), default="")
    land_no: Mapped[str] = mapped_column(String(50))
    area_sqm: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    land_use_zone: Mapped[str | None] = mapped_column(String(100))
    designated_use: Mapped[str | None] = mapped_column(String(100))
    ownership_numerator: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    ownership_denominator: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    source_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FormInstanceRecord(Base):
    __tablename__ = "form_instances"
    __table_args__ = {"schema": "valuation"}

    form_instance_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("valuation.cases.case_id")
    )
    form_code: Mapped[str] = mapped_column(String(10))
    version_no: Mapped[int] = mapped_column(default=1)
    form_status: Mapped[str] = mapped_column(String(30), default="DRAFT")
    form_content: Mapped[dict] = mapped_column(JSONB, default=dict)
    prepared_date: Mapped[date | None] = mapped_column(Date)
    source_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    output_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentRecord(Base):
    __tablename__ = "documents"
    __table_args__ = {"schema": "valuation"}

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("valuation.cases.case_id")
    )
    document_type: Mapped[str] = mapped_column(String(50))
    original_filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(100))
    bucket_name: Mapped[str] = mapped_column(String(63), default="land-valuation")
    object_key: Mapped[str] = mapped_column(String(1024), unique=True)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    file_size_bytes: Mapped[int] = mapped_column(BigInteger)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    document_group_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), default=uuid4
    )
    storage_etag: Mapped[str | None] = mapped_column(String(255))


class BenchmarkLandRecord(Base):
    __tablename__ = "benchmark_lands"
    __table_args__ = {"schema": "valuation"}

    benchmark_land_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    parcel_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    benchmark_land_no: Mapped[str] = mapped_column(String(30))
    price_zone_no: Mapped[str] = mapped_column(String(30))
    land_consolidation_serial: Mapped[str | None] = mapped_column(String(30))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FactorDefinitionRecord(Base):
    __tablename__ = "factor_definitions"
    __table_args__ = {"schema": "valuation"}

    factor_definition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    factor_code: Mapped[str] = mapped_column(String(50))
    factor_name: Mapped[str] = mapped_column(String(100))
    factor_category: Mapped[str] = mapped_column(String(50))
    data_type: Mapped[str] = mapped_column(String(20))
    unit: Mapped[str | None] = mapped_column(String(20))
    display_order: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class FactorLevelRecord(Base):
    __tablename__ = "factor_levels"
    __table_args__ = {"schema": "valuation"}

    factor_level_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    factor_definition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    rule_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    land_use_type: Mapped[str] = mapped_column(String(100))
    level_code: Mapped[str] = mapped_column(String(50))
    level_name: Mapped[str] = mapped_column(String(100))
    range_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    range_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    qualitative_value: Mapped[str | None] = mapped_column(String(200))
    suggested_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    maximum_impact_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    sort_order: Mapped[int] = mapped_column(Integer)


class ComparisonAnalysisRecord(Base):
    __tablename__ = "comparison_analyses"
    __table_args__ = {"schema": "valuation"}

    comparison_analysis_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    benchmark_land_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    form_instance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    valuation_base_date: Mapped[date] = mapped_column(Date)
    benchmark_comparison_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    benchmark_condition_notes: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    analysis_status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    rule_version_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    calculation_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    calculated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ComparisonTargetRecord(Base):
    __tablename__ = "comparison_targets"
    __table_args__ = {"schema": "valuation"}

    comparison_target_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    comparison_analysis_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    transaction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    display_order: Mapped[int] = mapped_column(Integer)
    normal_unit_price_snapshot: Mapped[Decimal] = mapped_column(Numeric(20, 2))
    transaction_date_snapshot: Mapped[date] = mapped_column(Date)
    time_adjustment_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), default=0
    )
    regional_adjustment_rate: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), default=0
    )
    total_adjustment_absolute: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    trial_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    weight: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    similarity_level: Mapped[str | None] = mapped_column(String(20))
    condition_notes: Mapped[str | None] = mapped_column(Text)


class ComparisonFactorValueRecord(Base):
    __tablename__ = "comparison_factor_values"
    __table_args__ = {"schema": "valuation"}

    factor_value_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    comparison_target_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    factor_definition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    factor_level_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    benchmark_factor_level_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    comparable_factor_level_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True)
    )
    benchmark_number: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    benchmark_text: Mapped[str | None] = mapped_column(Text)
    benchmark_json: Mapped[dict | list | str | int | bool | None] = mapped_column(
        JSONB
    )
    comparable_number: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    comparable_text: Mapped[str | None] = mapped_column(Text)
    comparable_json: Mapped[dict | list | str | int | bool | None] = mapped_column(
        JSONB
    )
    suggested_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    adopted_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=0)
    adjustment_reason: Mapped[str | None] = mapped_column(Text)


class BenchmarkValuationRecord(Base):
    __tablename__ = "benchmark_valuations"
    __table_args__ = {"schema": "valuation"}

    benchmark_valuation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    benchmark_land_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    comparison_analysis_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    form_instance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    valuation_base_date: Mapped[date] = mapped_column(Date)
    comparison_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    comparison_weight: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=1)
    income_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    income_weight: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=0)
    benchmark_land_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    market_period_start: Mapped[date | None] = mapped_column(Date)
    market_period_end: Mapped[date | None] = mapped_column(Date)
    market_condition: Mapped[str | None] = mapped_column(Text)
    selection_scope_reason: Mapped[str | None] = mapped_column(Text)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    valuation_status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class DocumentExtractionRecord(Base):
    __tablename__ = "document_extractions"
    __table_args__ = {"schema": "valuation"}

    extraction_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    provider: Mapped[str] = mapped_column(String(30))
    extraction_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    extracted_text: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ExtractedFieldRecord(Base):
    __tablename__ = "extracted_fields"
    __table_args__ = {"schema": "valuation"}

    extracted_field_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    extraction_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    form_code: Mapped[str] = mapped_column(String(10))
    field_name: Mapped[str] = mapped_column(String(100))
    extracted_value: Mapped[dict | list | str | int | bool] = mapped_column(JSONB)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4))
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_text: Mapped[str | None] = mapped_column(Text)
    analysis_provider: Mapped[str] = mapped_column(String(20), default="RULE")
    model_id: Mapped[str | None] = mapped_column(String(200))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    field_status: Mapped[str] = mapped_column(String(30), default="EXTRACTED")
    confirmed_value: Mapped[dict | list | str | int | bool | None] = mapped_column(
        JSONB
    )
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    applied_form_instance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssistantSessionRecord(Base):
    __tablename__ = "assistant_sessions"
    __table_args__ = {"schema": "valuation"}

    assistant_session_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    form_instance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    current_step: Mapped[str] = mapped_column(String(40), default="COLLECT_FIELDS")
    selected_form_type: Mapped[str] = mapped_column(String(50), default="F03")
    missing_fields: Mapped[list] = mapped_column(JSONB, default=list)
    missing_documents: Mapped[list] = mapped_column(JSONB, default=list)
    last_tool_name: Mapped[str | None] = mapped_column(String(100))
    last_tool_status: Mapped[str | None] = mapped_column(String(20))
    provider: Mapped[str] = mapped_column(String(20), default="MOCK")
    model_id: Mapped[str] = mapped_column(String(200))
    prompt_version: Mapped[str] = mapped_column(String(100))
    session_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssistantMessageRecord(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = {"schema": "valuation"}

    assistant_message_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    assistant_session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    message_no: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    tool_name: Mapped[str | None] = mapped_column(String(100))
    tool_input_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    tool_result_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    model_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ValuationResultRecord(Base):
    __tablename__ = "valuations"
    __table_args__ = {"schema": "valuation"}

    valuation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    parcel_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    form_instance_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    valuation_type: Mapped[str] = mapped_column(String(30))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    total_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    currency_code: Mapped[str] = mapped_column(String(3), default="TWD")
    calculation_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    result_status: Mapped[str] = mapped_column(String(20), default="CALCULATED")
    calculated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleVersionRecord(Base):
    __tablename__ = "rule_versions"
    __table_args__ = {"schema": "valuation"}

    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    rule_set_code: Mapped[str] = mapped_column(String(50))
    version_no: Mapped[int] = mapped_column(Integer)
    version_name: Mapped[str] = mapped_column(String(200))
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    effective_date_status: Mapped[str] = mapped_column(
        String(20), default="CONFIRMED"
    )
    status: Mapped[str] = mapped_column(String(20))
    source_reference: Mapped[str | None] = mapped_column(String(1000))
    source_checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    source_document_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    jurisdiction_code: Mapped[str | None] = mapped_column(String(50))
    district_scope: Mapped[dict | None] = mapped_column(JSONB)
    land_use_types: Mapped[list] = mapped_column(JSONB, default=list)
    formula_code: Mapped[str | None] = mapped_column(String(100))
    rounding_code: Mapped[str | None] = mapped_column(String(100))
    import_status: Mapped[str] = mapped_column(String(30), default="LEGACY")
    import_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RuleVersionSourceRecord(Base):
    __tablename__ = "rule_version_sources"
    __table_args__ = {"schema": "valuation"}

    rule_version_source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    rule_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("valuation.rule_versions.rule_version_id", ondelete="RESTRICT"),
    )
    source_document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("knowledge.documents.document_id", ondelete="RESTRICT"),
    )
    source_role: Mapped[str] = mapped_column(String(40))
    source_order: Mapped[int] = mapped_column(Integer)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True)
    source_reference: Mapped[str | None] = mapped_column(String(1000))
    page_reference: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("auth.users.user_id", ondelete="RESTRICT"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ValidationRuleRecord(Base):
    __tablename__ = "validation_rules"
    __table_args__ = {"schema": "valuation"}

    validation_rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    rule_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    rule_code: Mapped[str] = mapped_column(String(80))
    rule_name: Mapped[str] = mapped_column(String(200))
    target_form_code: Mapped[str | None] = mapped_column(String(10))
    target_table: Mapped[str] = mapped_column(String(100))
    target_field_code: Mapped[str | None] = mapped_column(String(100))
    severity: Mapped[str] = mapped_column(String(20))
    rule_expression: Mapped[str] = mapped_column(Text)
    message_template: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CaseEventRecord(Base):
    __tablename__ = "case_events"
    __table_args__ = {"schema": "history"}

    case_event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    case_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(80))
    event_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    occurred_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    request_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
