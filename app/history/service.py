from uuid import UUID

from app.core.exceptions import PermissionDeniedError, ResourceNotFoundError
from app.history.document_types import REVIEW_DOCUMENT_TYPES
from app.history.permissions import HistoryScope, history_scope
from app.history.repository import HistoryRepository
from app.history.schemas import (
    HistoryCaseDetail,
    HistoryCasePage,
    HistoryCaseSummary,
    HistoryCaseVersion,
    HistoryChange,
    HistoryDocument,
    HistoryPermissions,
    HistorySearchParams,
    HistoryVersionDiff,
    HistoryVersionValue,
)


class HistoryService:
    def __init__(self, session, repository: HistoryRepository | None = None) -> None:
        self.repository = repository or HistoryRepository(session)

    @staticmethod
    def scope(user) -> HistoryScope:
        return history_scope(user)

    @staticmethod
    def permissions(scope: HistoryScope) -> HistoryPermissions:
        return HistoryPermissions(
            can_view_valuation=scope.valuation,
            can_view_review=scope.review,
        )

    async def search(self, params: HistorySearchParams, user) -> HistoryCasePage:
        scope = self.scope(user)
        if not scope.review and (
            params.sort in {"received_at", "risk_level"}
            or params.date_field in {"received_at", "completed_at"}
            or params.result in {"PASSED", "RETURNED", "SUPPLEMENT_REQUIRED"}
        ):
            raise PermissionDeniedError("此搜尋條件包含不可調閱的審查資料")
        rows, total = await self.repository.search(params, scope)
        items = []
        for row in rows:
            modules = []
            if scope.valuation and (row["valuation_data"] or row["valuation_documents"]):
                modules.append("valuation")
            if scope.review and (row["review_data"] or row["review_documents"]):
                modules.append("review")
            if not scope.review:
                row["review_status"] = None
                row["received_at"] = None
                row["completed_at"] = None
                row["current_risk_level"] = None
            items.append(
                HistoryCaseSummary(
                    **row,
                    visible_modules=modules,
                    has_structured_data=(
                        (scope.valuation and row["valuation_data"])
                        or (scope.review and row["review_data"])
                    ),
                    has_document_metadata=(
                        (scope.valuation and row["valuation_documents"])
                        or (scope.review and row["review_documents"])
                    ),
                )
            )
        return HistoryCasePage(
            items=items,
            total=total,
            offset=params.offset,
            limit=params.limit,
            permissions=self.permissions(scope),
        )

    async def detail(self, case_id: UUID, user) -> HistoryCaseDetail:
        scope = self.scope(user)
        case = await self.repository.get_case(case_id)
        if case is None:
            raise ResourceNotFoundError("案件")
        access = await self.repository.case_access(case_id, scope)
        if not access.get("allowed"):
            raise PermissionDeniedError("沒有可調閱的案件歷史資料")
        documents = await self.repository.list_documents(case_id, scope)
        versions = await self.repository.list_case_versions(case_id)
        changes = (
            await self.repository.list_changes(case_id)
            if scope.valuation and scope.review
            else []
        )
        version_diffs = (
            self._version_diffs(await self.repository.list_official_field_versions(case_id))
            if scope.valuation
            else []
        )
        return HistoryCaseDetail(
            case=case,
            parcels=(
                await self.repository.list_parcels(case_id) if scope.valuation else []
            ),
            documents=[self._document(item) for item in documents],
            valuation=(
                await self.repository.valuation_data(case_id) if scope.valuation else None
            ),
            review=await self.repository.review_data(case_id) if scope.review else None,
            versions=[HistoryCaseVersion(**item) for item in versions],
            changes=[HistoryChange(**item) for item in changes],
            version_diffs=version_diffs,
            permissions=self.permissions(scope),
        )

    async def document(self, document_id: UUID, user) -> dict:
        scope = self.scope(user)
        document = await self.repository.get_document(document_id, scope)
        if document is None:
            raise ResourceNotFoundError("文件")
        return document

    @staticmethod
    def _version_diffs(rows: list[dict]) -> list[HistoryVersionDiff]:
        grouped: dict[tuple[object, str, str | None], list[dict]] = {}
        for row in rows:
            key = (row["document_group_id"], row["field_code"], row.get("field_path"))
            grouped.setdefault(key, []).append(row)
        diffs: list[HistoryVersionDiff] = []
        for (_, field_code, field_path), versions in sorted(
            grouped.items(), key=lambda item: (str(item[0][0]), item[0][1], item[0][2] or "")
        ):
            if len(versions) < 2:
                continue
            previous, current = versions[-2:]
            if previous.get("normalized_value") == current.get("normalized_value"):
                continue
            diffs.append(
                HistoryVersionDiff(
                    field_code=field_code,
                    field_path=field_path,
                    previous=HistoryVersionValue(
                        document_version=previous["document_version"],
                        value=previous.get("normalized_value"),
                        raw_text=previous.get("raw_text") or None,
                        page_number=previous.get("page_number"),
                    ),
                    current=HistoryVersionValue(
                        document_version=current["document_version"],
                        value=current.get("normalized_value"),
                        raw_text=current.get("raw_text") or None,
                        page_number=current.get("page_number"),
                    ),
                )
            )
        return diffs

    @staticmethod
    def _document(row: dict) -> HistoryDocument:
        source = "review" if row["document_type"] in REVIEW_DOCUMENT_TYPES else "valuation"
        return HistoryDocument(
            document_id=row["document_id"],
            case_id=row["case_id"],
            document_type=row["document_type"],
            source_module=source,
            object_key=row["object_key"],
            file_name=row["original_filename"],
            content_type=row["mime_type"],
            created_at=row["uploaded_at"],
            document_group_id=row["document_group_id"],
            version_no=row["version_no"],
            is_active=row["is_active"],
            file_size_bytes=row["file_size_bytes"],
            checksum_sha256=row["checksum_sha256"],
            download_available=None,
        )
