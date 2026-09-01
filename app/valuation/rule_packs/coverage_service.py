from __future__ import annotations

from datetime import date

from app.core.exceptions import AppError
from app.valuation.models import RuleVersionRecord
from app.valuation.rule_packs.coverage import (
    NEW_TAIPEI_DISTRICT_CODES,
    NEW_TAIPEI_DISTRICTS,
    rule_covers,
)
from app.valuation.rule_packs.repository import RulePackRepository
from app.valuation.rule_packs.schemas import (
    LandUseType,
    RuleCoverageMatch,
    RuleCoverageMatrixResponse,
    RuleCoverageResponse,
)


class RuleCoverageService:
    def __init__(self, repository: RulePackRepository) -> None:
        self.repository = repository

    async def check(
        self,
        *,
        district_code: str,
        land_use_type: LandUseType | str,
        valuation_date: date,
        candidates: list[RuleVersionRecord] | None = None,
    ) -> RuleCoverageResponse:
        if district_code not in NEW_TAIPEI_DISTRICT_CODES:
            raise AppError(
                "NTPC_DISTRICT_INVALID",
                "行政區代碼不屬於新北市29區",
                422,
                {"district_code": district_code},
            )
        try:
            normalized_land_use = LandUseType(land_use_type)
        except ValueError as exc:
            raise AppError(
                "LAND_USE_TYPE_INVALID",
                "土地用途必須是住宅、商業、工業、農業或其他用途之一",
                422,
                {"land_use_type": str(land_use_type)},
            ) from exc

        values = (
            candidates
            if candidates is not None
            else await self.repository.list_effective_published(valuation_date)
        )
        matches = [
            item
            for item in values
            if rule_covers(
                item,
                district_code=district_code,
                land_use_type=normalized_land_use.value,
                valuation_date=valuation_date,
            )
        ]
        match_responses = [self._match(item) for item in matches]
        if not matches:
            status = "MISSING"
            message = "找不到符合行政區、土地用途及估價基準日的已發布正式規則"
        elif len(matches) > 1:
            status = "AMBIGUOUS"
            message = "同一適用條件存在多個正式規則版本，必須先排除重疊"
        else:
            status = "COVERED"
            message = "已有唯一且有效的正式規則版本"
        return RuleCoverageResponse(
            district_code=district_code,
            district_name=NEW_TAIPEI_DISTRICTS[district_code],
            land_use_type=normalized_land_use,
            valuation_date=valuation_date,
            status=status,
            covered=status == "COVERED",
            matches=match_responses,
            message=message,
        )

    async def require(
        self,
        *,
        district_code: str,
        land_use_type: LandUseType | str,
        valuation_date: date,
    ) -> RuleVersionRecord:
        candidates = await self.repository.list_effective_published(valuation_date)
        response = await self.check(
            district_code=district_code,
            land_use_type=land_use_type,
            valuation_date=valuation_date,
            candidates=candidates,
        )
        if response.status == "MISSING":
            raise AppError(
                "RULE_COVERAGE_MISSING",
                response.message,
                409,
                response.model_dump(mode="json"),
            )
        if response.status == "AMBIGUOUS":
            raise AppError(
                "RULE_COVERAGE_AMBIGUOUS",
                response.message,
                409,
                response.model_dump(mode="json"),
            )
        rule_version_id = response.matches[0].rule_version_id
        return next(
            item for item in candidates if item.rule_version_id == rule_version_id
        )

    async def matrix(self, valuation_date: date) -> RuleCoverageMatrixResponse:
        candidates = await self.repository.list_effective_published(valuation_date)
        items = [
            await self.check(
                district_code=district_code,
                land_use_type=land_use_type,
                valuation_date=valuation_date,
                candidates=candidates,
            )
            for district_code in NEW_TAIPEI_DISTRICTS
            for land_use_type in LandUseType
        ]
        return RuleCoverageMatrixResponse(
            valuation_date=valuation_date,
            total_combinations=len(items),
            covered_count=sum(item.status == "COVERED" for item in items),
            missing_count=sum(item.status == "MISSING" for item in items),
            ambiguous_count=sum(item.status == "AMBIGUOUS" for item in items),
            items=items,
        )

    @staticmethod
    def _match(rule: RuleVersionRecord) -> RuleCoverageMatch:
        if rule.effective_from is None:
            raise ValueError("Published rule is missing effective_from")
        return RuleCoverageMatch(
            rule_version_id=rule.rule_version_id,
            rule_set_code=rule.rule_set_code,
            version_no=rule.version_no,
            version_name=rule.version_name,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
        )

