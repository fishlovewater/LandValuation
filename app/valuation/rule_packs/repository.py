from datetime import date
from uuid import UUID

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.models import KnowledgeDocumentRecord
from app.valuation.models import (
    FactorDefinitionRecord,
    FactorLevelRecord,
    RuleVersionRecord,
    RuleVersionSourceRecord,
)


class RulePackRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def next_version(self, rule_set_code: str) -> int:
        latest = await self.session.scalar(
            select(func.max(RuleVersionRecord.version_no)).where(
                RuleVersionRecord.rule_set_code == rule_set_code
            )
        )
        return (latest or 0) + 1

    async def create_source(
        self,
        document: KnowledgeDocumentRecord,
        rule: RuleVersionRecord,
        source_link: RuleVersionSourceRecord,
    ) -> RuleVersionRecord:
        self.session.add(document)
        await self.session.flush()
        self.session.add(rule)
        await self.session.flush()
        self.session.add(source_link)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def add_source(
        self,
        document: KnowledgeDocumentRecord,
        source_link: RuleVersionSourceRecord,
    ) -> RuleVersionSourceRecord:
        self.session.add(document)
        await self.session.flush()
        self.session.add(source_link)
        await self.session.flush()
        await self.session.refresh(source_link)
        return source_link

    async def add_source_link(
        self, source_link: RuleVersionSourceRecord
    ) -> RuleVersionSourceRecord:
        self.session.add(source_link)
        await self.session.flush()
        await self.session.refresh(source_link)
        return source_link

    async def create_rule_with_source_link(
        self,
        rule: RuleVersionRecord,
        source_link: RuleVersionSourceRecord,
    ) -> RuleVersionRecord:
        self.session.add(rule)
        await self.session.flush()
        self.session.add(source_link)
        await self.session.flush()
        await self.session.refresh(rule)
        return rule

    async def get(self, rule_version_id: UUID) -> RuleVersionRecord | None:
        return await self.session.scalar(
            select(RuleVersionRecord).where(
                RuleVersionRecord.rule_version_id == rule_version_id
            )
        )

    async def list_all(self) -> list[RuleVersionRecord]:
        values = await self.session.scalars(
            select(RuleVersionRecord)
            .where(RuleVersionRecord.jurisdiction_code == "NEW_TAIPEI_CITY")
            .order_by(RuleVersionRecord.rule_set_code, RuleVersionRecord.version_no.desc())
        )
        return list(values.all())

    async def list_published(self) -> list[RuleVersionRecord]:
        values = await self.session.scalars(
            select(RuleVersionRecord)
            .where(
                RuleVersionRecord.jurisdiction_code == "NEW_TAIPEI_CITY",
                RuleVersionRecord.status == "PUBLISHED",
            )
            .order_by(
                RuleVersionRecord.effective_from,
                RuleVersionRecord.rule_set_code,
                RuleVersionRecord.version_no,
            )
        )
        return list(values.all())

    async def list_effective_published(
        self, valuation_date: date
    ) -> list[RuleVersionRecord]:
        values = await self.session.scalars(
            select(RuleVersionRecord)
            .where(
                RuleVersionRecord.jurisdiction_code == "NEW_TAIPEI_CITY",
                RuleVersionRecord.status == "PUBLISHED",
                RuleVersionRecord.effective_from.is_not(None),
                RuleVersionRecord.effective_from <= valuation_date,
                or_(
                    RuleVersionRecord.effective_to.is_(None),
                    RuleVersionRecord.effective_to >= valuation_date,
                ),
            )
            .order_by(
                RuleVersionRecord.rule_set_code,
                RuleVersionRecord.version_no.desc(),
            )
        )
        return list(values.all())

    async def get_source(self, document_id: UUID) -> KnowledgeDocumentRecord | None:
        return await self.session.scalar(
            select(KnowledgeDocumentRecord).where(
                KnowledgeDocumentRecord.document_id == document_id
            )
        )

    async def list_available_knowledge_sources(self) -> list[KnowledgeDocumentRecord]:
        values = await self.session.scalars(
            select(KnowledgeDocumentRecord)
            .where(
                KnowledgeDocumentRecord.object_key.like("knowledge/%"),
                ~KnowledgeDocumentRecord.object_key.like("knowledge/rule-sources/%"),
            )
            .order_by(
                KnowledgeDocumentRecord.document_type,
                KnowledgeDocumentRecord.title,
                KnowledgeDocumentRecord.version_no.desc(),
            )
        )
        return list(values.all())

    async def next_source_order(self, rule_version_id: UUID) -> int:
        latest = await self.session.scalar(
            select(func.max(RuleVersionSourceRecord.source_order)).where(
                RuleVersionSourceRecord.rule_version_id == rule_version_id
            )
        )
        return (latest or 0) + 1

    async def list_sources(
        self, rule_version_id: UUID
    ) -> list[tuple[RuleVersionSourceRecord, KnowledgeDocumentRecord]]:
        rows = await self.session.execute(
            select(RuleVersionSourceRecord, KnowledgeDocumentRecord)
            .join(
                KnowledgeDocumentRecord,
                KnowledgeDocumentRecord.document_id
                == RuleVersionSourceRecord.source_document_id,
            )
            .where(RuleVersionSourceRecord.rule_version_id == rule_version_id)
            .order_by(RuleVersionSourceRecord.source_order)
        )
        return list(rows.tuples().all())

    async def get_rule_source(
        self, rule_version_id: UUID, rule_version_source_id: UUID
    ) -> tuple[RuleVersionSourceRecord, KnowledgeDocumentRecord] | None:
        row = await self.session.execute(
            select(RuleVersionSourceRecord, KnowledgeDocumentRecord)
            .join(
                KnowledgeDocumentRecord,
                KnowledgeDocumentRecord.document_id
                == RuleVersionSourceRecord.source_document_id,
            )
            .where(
                RuleVersionSourceRecord.rule_version_id == rule_version_id,
                RuleVersionSourceRecord.rule_version_source_id
                == rule_version_source_id,
            )
        )
        return row.tuples().one_or_none()

    async def matching_definitions(
        self, codes: set[str], orders: set[int]
    ) -> list[FactorDefinitionRecord]:
        values = await self.session.scalars(
            select(FactorDefinitionRecord).where(
                or_(
                    FactorDefinitionRecord.factor_code.in_(codes),
                    FactorDefinitionRecord.display_order.in_(orders),
                )
            )
        )
        return list(values.all())

    async def replace_levels(
        self,
        rule_version_id: UUID,
        new_definitions: list[FactorDefinitionRecord],
        levels: list[FactorLevelRecord],
    ) -> None:
        await self.session.execute(
            delete(FactorLevelRecord).where(
                FactorLevelRecord.rule_version_id == rule_version_id
            )
        )
        self.session.add_all(new_definitions)
        await self.session.flush()
        self.session.add_all(levels)
        await self.session.flush()

    async def level_land_uses(self, rule_version_id: UUID) -> set[str]:
        values = await self.session.scalars(
            select(FactorLevelRecord.land_use_type)
            .where(FactorLevelRecord.rule_version_id == rule_version_id)
            .distinct()
        )
        return set(values.all())

    async def level_count(self, rule_version_id: UUID) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(FactorLevelRecord).where(
                    FactorLevelRecord.rule_version_id == rule_version_id
                )
            )
            or 0
        )

    async def audit_levels(
        self, rule_version_id: UUID
    ) -> list[tuple[FactorDefinitionRecord, FactorLevelRecord]]:
        rows = await self.session.execute(
            select(FactorDefinitionRecord, FactorLevelRecord)
            .join(
                FactorLevelRecord,
                FactorLevelRecord.factor_definition_id
                == FactorDefinitionRecord.factor_definition_id,
            )
            .where(FactorLevelRecord.rule_version_id == rule_version_id)
            .order_by(
                FactorDefinitionRecord.display_order,
                FactorLevelRecord.land_use_type,
                FactorLevelRecord.sort_order,
            )
        )
        return list(rows.tuples().all())

    async def save(self, rule: RuleVersionRecord) -> RuleVersionRecord:
        await self.session.flush()
        await self.session.refresh(rule)
        return rule
