from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.exceptions import AppError
from app.valuation.models import (
    BenchmarkLandRecord,
    ComparisonAnalysisRecord,
    ComparisonTargetRecord,
    ParcelRecord,
    TransactionCaseRecord,
)
from app.valuation.report_packages.page_schemas import (
    F02DraftData,
    F02RFDraftData,
    F02TargetSelection,
)
from app.valuation.report_packages.page_service import ReportPageService
from app.valuation.schemas import RequestModel
from app.valuation.service import ValuationService


class ComparisonSetupTarget(RequestModel):
    transaction_no: str = Field(min_length=1, max_length=80)
    transaction_date: date
    transaction_total_price: Decimal = Field(
        gt=0, max_digits=20, decimal_places=2
    )
    normal_land_unit_price: Decimal = Field(
        gt=0, max_digits=20, decimal_places=2
    )
    weight: Decimal = Field(gt=0, le=1, max_digits=9, decimal_places=6)
    source_notes: str = Field(min_length=1, max_length=1000)
    subject_address: str | None = Field(default=None, max_length=500)
    land_area_sqm: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=4
    )


class ComparisonSetupCreate(RequestModel):
    report_id: UUID
    benchmark_land_id: UUID
    targets: list[ComparisonSetupTarget] = Field(min_length=1, max_length=3)
    notes: str | None = Field(default=None, max_length=3000)

    @model_validator(mode="after")
    def validate_targets(self):
        numbers = [item.transaction_no for item in self.targets]
        if len(numbers) != len(set(numbers)):
            raise ValueError("比較標的交易編號不可重複")
        if sum((item.weight for item in self.targets), Decimal("0")) != Decimal("1"):
            raise ValueError("比較標的權重合計必須為 1")
        return self


class ComparisonSetupApply(RequestModel):
    report_id: UUID
    comparison_analysis_id: UUID


class ComparisonSetupTargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comparison_target_id: UUID
    transaction_id: UUID
    transaction_no: str
    transaction_date: date
    normal_land_unit_price: Decimal
    weight: Decimal


class ComparisonSetupResponse(BaseModel):
    comparison_analysis_id: UUID
    benchmark_land_id: UUID
    report_id: UUID
    targets: list[ComparisonSetupTargetResponse]


class ComparisonSetupContext(BaseModel):
    parcels: list[dict]
    benchmark_lands: list[dict]
    analyses: list[dict]


class ComparisonSetupService:
    """Creates traceable comparison inputs without inventing market evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.valuation = ValuationService(session)

    async def context(self, case_id: UUID, user: User) -> ComparisonSetupContext:
        await self.valuation.get_case(case_id, user)
        parcels = list(
            (
                await self.session.scalars(
                    select(ParcelRecord)
                    .where(ParcelRecord.case_id == case_id)
                    .order_by(ParcelRecord.section_name, ParcelRecord.land_no)
                )
            ).all()
        )
        benchmarks = list(
            (
                await self.session.scalars(
                    select(BenchmarkLandRecord)
                    .where(
                        BenchmarkLandRecord.case_id == case_id,
                        BenchmarkLandRecord.is_active.is_(True),
                    )
                    .order_by(BenchmarkLandRecord.benchmark_land_no)
                )
            ).all()
        )
        analyses = list(
            (
                await self.session.scalars(
                    select(ComparisonAnalysisRecord)
                    .where(
                        ComparisonAnalysisRecord.case_id == case_id,
                        ComparisonAnalysisRecord.analysis_status != "VOID",
                    )
                    .order_by(ComparisonAnalysisRecord.created_at.desc())
                )
            ).all()
        )
        target_counts = dict(
            (
                await self.session.execute(
                    select(
                        ComparisonTargetRecord.comparison_analysis_id,
                        func.count(ComparisonTargetRecord.comparison_target_id),
                    )
                    .where(ComparisonTargetRecord.case_id == case_id)
                    .group_by(ComparisonTargetRecord.comparison_analysis_id)
                )
            ).all()
        )
        return ComparisonSetupContext(
            parcels=[
                {
                    "parcel_id": str(item.parcel_id),
                    "label": " ".join(
                        part
                        for part in (item.section_name, item.subsection_name, item.land_no)
                        if part
                    ),
                }
                for item in parcels
            ],
            benchmark_lands=[
                {
                    "benchmark_land_id": str(item.benchmark_land_id),
                    "label": f"{item.benchmark_land_no}｜價格區段 {item.price_zone_no}",
                }
                for item in benchmarks
            ],
            analyses=[
                {
                    "comparison_analysis_id": str(item.comparison_analysis_id),
                    "benchmark_land_id": str(item.benchmark_land_id),
                    "analysis_status": item.analysis_status,
                    "label": (
                        f"{item.comparison_analysis_id}｜"
                        f"{target_counts.get(item.comparison_analysis_id, 0)} 筆比較標的"
                    ),
                }
                for item in analyses
            ],
        )

    async def create(
        self, case_id: UUID, payload: ComparisonSetupCreate, user: User
    ) -> ComparisonSetupResponse:
        pages = ReportPageService(self.session)
        case, records = await pages._editable_records(case_id, payload.report_id, user)
        benchmark = await pages.repository.get_benchmark_land(
            case_id, payload.benchmark_land_id
        )
        if benchmark is None:
            raise AppError("BENCHMARK_LAND_NOT_FOUND", "找不到案件的比準地", 422)
        existing = await self.session.scalar(
            select(ComparisonAnalysisRecord).where(
                ComparisonAnalysisRecord.case_id == case_id,
                ComparisonAnalysisRecord.form_instance_id
                == records["F02"].form_instance_id,
                ComparisonAnalysisRecord.analysis_status != "VOID",
            )
        )
        if existing is not None:
            raise AppError(
                "COMPARISON_SETUP_EXISTS",
                "此正式表單已建立比較分析；請建立新的正式表單版本後再重做",
                409,
            )
        duplicate_numbers = list(
            (
                await self.session.scalars(
                    select(TransactionCaseRecord.transaction_no).where(
                        TransactionCaseRecord.case_id == case_id,
                        TransactionCaseRecord.transaction_no.in_(
                            [item.transaction_no for item in payload.targets]
                        ),
                    )
                )
            ).all()
        )
        if duplicate_numbers:
            raise AppError(
                "TRANSACTION_NO_ALREADY_EXISTS",
                "案件內已有相同交易編號，請使用新的正式表單版本或不同交易資料",
                409,
                {"transaction_nos": sorted(duplicate_numbers)},
            )

        analysis = ComparisonAnalysisRecord(
            case_id=case_id,
            benchmark_land_id=benchmark.benchmark_land_id,
            form_instance_id=records["F02"].form_instance_id,
            valuation_base_date=case.valuation_base_date,
            notes=payload.notes,
            analysis_status="DRAFT",
        )
        self.session.add(analysis)
        await self.session.flush()

        response_targets: list[ComparisonSetupTargetResponse] = []
        f02_targets: list[F02TargetSelection] = []
        for display_order, item in enumerate(payload.targets, start=1):
            transaction = TransactionCaseRecord(
                case_id=case_id,
                transaction_no=item.transaction_no,
                transaction_date=item.transaction_date,
                transaction_total_price=item.transaction_total_price,
                normal_land_unit_price=item.normal_land_unit_price,
                subject_address=item.subject_address,
                land_area_sqm=item.land_area_sqm,
                notes=item.source_notes,
                record_status="READY",
            )
            self.session.add(transaction)
            await self.session.flush()
            target = ComparisonTargetRecord(
                case_id=case_id,
                comparison_analysis_id=analysis.comparison_analysis_id,
                transaction_id=transaction.transaction_id,
                display_order=display_order,
                normal_unit_price_snapshot=item.normal_land_unit_price,
                transaction_date_snapshot=item.transaction_date,
                weight=item.weight,
                condition_notes=item.source_notes,
            )
            self.session.add(target)
            await self.session.flush()
            response_targets.append(
                ComparisonSetupTargetResponse(
                    comparison_target_id=target.comparison_target_id,
                    transaction_id=transaction.transaction_id,
                    transaction_no=transaction.transaction_no,
                    transaction_date=transaction.transaction_date,
                    normal_land_unit_price=transaction.normal_land_unit_price,
                    weight=target.weight,
                )
            )
            f02_targets.append(
                F02TargetSelection(
                    comparison_target_id=target.comparison_target_id,
                    display_order=display_order,
                    time_adjustment_rate=Decimal("0"),
                    weight=item.weight,
                    weight_reason=item.source_notes,
                    weight_confirmed_by_user=True,
                )
            )

        regional = pages._read_data(records["F02-RF"], F02RFDraftData)
        comparison = pages._read_data(records["F02"], F02DraftData)
        regional.benchmark_land_id = benchmark.benchmark_land_id
        regional.comparison_analysis_id = analysis.comparison_analysis_id
        pages._invalidate_f02_rf_calculation(regional)
        comparison.benchmark_land_id = benchmark.benchmark_land_id
        comparison.comparison_analysis_id = analysis.comparison_analysis_id
        comparison.comparison_targets = f02_targets
        pages._invalidate_f02_calculation(comparison)
        pages._validate_cross_page_ids(regional, comparison)
        await pages._save_data(records["F02-RF"], regional, user)
        await pages._save_data(records["F02"], comparison, user)
        await self.session.flush()
        return ComparisonSetupResponse(
            comparison_analysis_id=analysis.comparison_analysis_id,
            benchmark_land_id=benchmark.benchmark_land_id,
            report_id=payload.report_id,
            targets=response_targets,
        )

    async def apply(
        self, case_id: UUID, payload: ComparisonSetupApply, user: User
    ) -> ComparisonSetupResponse:
        pages = ReportPageService(self.session)
        _, records = await pages._editable_records(case_id, payload.report_id, user)
        analysis = await self.session.scalar(
            select(ComparisonAnalysisRecord).where(
                ComparisonAnalysisRecord.case_id == case_id,
                ComparisonAnalysisRecord.comparison_analysis_id
                == payload.comparison_analysis_id,
                ComparisonAnalysisRecord.analysis_status != "VOID",
            )
        )
        if analysis is None:
            raise AppError("COMPARISON_ANALYSIS_NOT_FOUND", "找不到案件的比較分析", 422)
        if analysis.form_instance_id not in (None, records["F02"].form_instance_id):
            raise AppError(
                "COMPARISON_ANALYSIS_REPORT_CONFLICT",
                "此比較分析已連結其他正式表單版本，請選擇相同表單或建立新分析",
                409,
            )
        benchmark = await pages.repository.get_benchmark_land(
            case_id, analysis.benchmark_land_id
        )
        targets = await pages.repository.list_comparison_targets(
            case_id, analysis.comparison_analysis_id
        )
        if benchmark is None or not 1 <= len(targets) <= 3:
            raise AppError(
                "COMPARISON_ANALYSIS_NOT_READY",
                "比較分析必須保有有效比準地與 1 至 3 筆比較標的",
                422,
            )
        transactions = {
            item.transaction_id: item
            for item in (
                await self.session.scalars(
                    select(TransactionCaseRecord).where(
                        TransactionCaseRecord.case_id == case_id,
                        TransactionCaseRecord.transaction_id.in_(
                            [item.transaction_id for item in targets]
                        ),
                    )
                )
            ).all()
        }
        f02_targets: list[F02TargetSelection] = []
        response_targets: list[ComparisonSetupTargetResponse] = []
        for target in sorted(targets, key=lambda item: item.display_order):
            transaction = transactions.get(target.transaction_id)
            if transaction is None or target.weight is None or not target.condition_notes:
                raise AppError(
                    "COMPARISON_TARGET_NOT_READY",
                    "既有比較標的缺少交易、已確認權重或來源說明",
                    422,
                    {"comparison_target_id": str(target.comparison_target_id)},
                )
            if target.time_adjustment_rate != 0:
                raise AppError(
                    "COMPARISON_TARGET_NOT_READY",
                    "非零日期調整須先在 F02 補上人工確認與來源說明",
                    422,
                    {"comparison_target_id": str(target.comparison_target_id)},
                )
            f02_targets.append(
                F02TargetSelection(
                    comparison_target_id=target.comparison_target_id,
                    display_order=target.display_order,
                    time_adjustment_rate=Decimal("0"),
                    weight=target.weight,
                    weight_reason=target.condition_notes,
                    weight_confirmed_by_user=True,
                )
            )
            response_targets.append(
                ComparisonSetupTargetResponse(
                    comparison_target_id=target.comparison_target_id,
                    transaction_id=transaction.transaction_id,
                    transaction_no=transaction.transaction_no,
                    transaction_date=transaction.transaction_date,
                    normal_land_unit_price=target.normal_unit_price_snapshot,
                    weight=target.weight,
                )
            )

        analysis.form_instance_id = records["F02"].form_instance_id
        regional = pages._read_data(records["F02-RF"], F02RFDraftData)
        comparison = pages._read_data(records["F02"], F02DraftData)
        regional.benchmark_land_id = benchmark.benchmark_land_id
        regional.comparison_analysis_id = analysis.comparison_analysis_id
        pages._invalidate_f02_rf_calculation(regional)
        comparison.benchmark_land_id = benchmark.benchmark_land_id
        comparison.comparison_analysis_id = analysis.comparison_analysis_id
        comparison.comparison_targets = f02_targets
        pages._invalidate_f02_calculation(comparison)
        pages._validate_cross_page_ids(regional, comparison)
        await pages._save_data(records["F02-RF"], regional, user)
        await pages._save_data(records["F02"], comparison, user)
        await self.session.flush()
        return ComparisonSetupResponse(
            comparison_analysis_id=analysis.comparison_analysis_id,
            benchmark_land_id=benchmark.benchmark_land_id,
            report_id=payload.report_id,
            targets=response_targets,
        )
