from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.knowledge.schemas import (
    KnowledgeAnswerResponse,
    KnowledgeAnswerStatus,
    KnowledgeCitation,
    KnowledgeRetrievalStatus,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeUnreadableSource,
)
from app.knowledge.source_policy import is_example_reference


@dataclass(frozen=True)
class RetrievedKnowledge:
    document: object
    chunk: object


def _terms(question: str) -> set[str]:
    normalized = question.lower().strip()
    latin = set(re.findall(r"[a-z0-9_]{2,}", normalized))
    chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
    bigrams = {
        run[index : index + 2]
        for run in chinese_runs
        for index in range(len(run) - 1)
    }
    return latin | bigrams


def _excerpt(content: str, limit: int = 360) -> str:
    compact = " ".join(content.split())
    return compact if len(compact) <= limit else f"{compact[: limit - 3]}..."


_ARTICLE_QUOTE_PATTERN = re.compile(
    r"第\s*[0-9０-９一二三四五六七八九十百千之\-]+\s*條"
)


def _article_no_from_supporting_quote(value: str | None) -> str | None:
    if not value:
        return None
    match = _ARTICLE_QUOTE_PATTERN.search(value)
    return " ".join(match.group(0).split()) if match else None


class KnowledgeSafetyService:
    """Ranks authorized MinIO sources and never creates unsupported facts."""

    def rank(
        self,
        request: KnowledgeSearchRequest,
        candidates: Iterable[RetrievedKnowledge],
        *,
        limit: int | None = None,
    ) -> list[RetrievedKnowledge]:
        normalized_question = request.question.lower().strip()
        ranked: list[tuple[int, RetrievedKnowledge]] = []
        for item in candidates:
            document = item.document
            chunk = item.chunk
            if is_example_reference(document):
                continue
            if request.as_of_date and not self._effective_on(document, request.as_of_date):
                continue
            if request.document_types and getattr(document, "document_type", None) not in request.document_types:
                continue
            document_title = str(getattr(document, "title", "") or "").lower().strip()
            title_is_explicit = bool(document_title and document_title in normalized_question)
            topic_question = (
                normalized_question.replace(document_title, " ")
                if title_is_explicit
                else normalized_question
            )
            terms = _terms(topic_question)
            topic_haystack = " ".join(
                str(value or "")
                for value in (
                    getattr(chunk, "section_title", None),
                    getattr(chunk, "article_no", None),
                    getattr(chunk, "content", None),
                )
            ).lower()
            score = sum(term in topic_haystack for term in terms)
            if title_is_explicit and score:
                score += max(20, len(terms) * 2)
            elif not title_is_explicit:
                full_haystack = f"{document_title} {topic_haystack}"
                score = sum(term in full_haystack for term in terms)
            if score:
                ranked.append((score, item))
        ranked.sort(
            key=lambda pair: (pair[0], getattr(pair[1].chunk, "chunk_no", 0)),
            reverse=True,
        )
        return [item for _, item in ranked[: limit or request.limit]]

    @staticmethod
    def _effective_on(document: object, as_of_date: date) -> bool:
        effective_from = getattr(document, "effective_from", None)
        effective_to = getattr(document, "effective_to", None)
        return not (
            (effective_from is not None and effective_from > as_of_date)
            or (effective_to is not None and effective_to < as_of_date)
        )

    def search_response(
        self,
        request: KnowledgeSearchRequest,
        candidates: Iterable[RetrievedKnowledge],
        unreadable_sources: Iterable[object] = (),
    ) -> KnowledgeSearchResponse:
        ranked = self.rank(request, candidates)
        return KnowledgeSearchResponse(
            retrieval_status=(
                KnowledgeRetrievalStatus.CANDIDATES_FOUND
                if ranked
                else KnowledgeRetrievalStatus.NO_RELEVANT_SOURCE
            ),
            retrieval_notice=(
                "這是關鍵字相符的候選來源，尚未經 AI 逐項驗證是否支持答案；"
                "請使用 /ask 取得具證據核對的回答。"
                if ranked
                else "找不到與問題相符的可讀來源。"
            ),
            citations=[self._citation(item) for item in ranked],
            unreadable_sources=[self._unreadable_source(item) for item in unreadable_sources],
        )

    def evidence_only_answer(
        self,
        request: KnowledgeSearchRequest,
        candidates: Iterable[RetrievedKnowledge],
        unreadable_sources: Iterable[object] = (),
    ) -> KnowledgeAnswerResponse:
        result = self.search_response(request, candidates, unreadable_sources)
        if not result.citations:
            return KnowledgeAnswerResponse(
                answer_status=KnowledgeAnswerStatus.NO_RELEVANT_SOURCE,
                citations=result.citations,
                unreadable_sources=result.unreadable_sources,
                answer="目前可讀取且適用的知識文件中，找不到足以支持此問題的來源。",
                generation_mode="EVIDENCE_ONLY",
                next_action="ASK_FOR_CLARIFICATION_OR_PUBLISH_RELEVANT_SOURCE",
            )
        return KnowledgeAnswerResponse(
            answer_status=KnowledgeAnswerStatus.EVIDENCE_ONLY,
            citations=result.citations,
            unreadable_sources=result.unreadable_sources,
            answer=(
                "已找到可供查核的來源資料；目前僅提供可核對的來源內容，"
                "不會自行補充未收錄的結論。"
            ),
            generation_mode="EVIDENCE_ONLY",
            next_action="REVIEW_CITED_SOURCES",
        )

    def ai_answer_response(
        self,
        answer,
        candidates: Iterable[RetrievedKnowledge],
        *,
        provider_name: str,
        model_id: str | None,
        unreadable_sources: Iterable[object] = (),
    ) -> KnowledgeAnswerResponse:
        """Convert a validated Codex answer into citations owned by this API."""

        cited_ids = set(answer.cited_chunk_ids)
        candidates_by_chunk_id = {
            item.chunk.chunk_id: item
            for item in candidates
            if item.chunk.chunk_id in cited_ids
        }
        evidence_by_chunk_id = {item.chunk_id: item for item in answer.evidence}
        # ``parse_answer`` normally guarantees these invariants.  Keep this
        # boundary check as well: provider output must never be able to turn a
        # malformed citation map into an unhelpful HTTP 500.
        if (
            len(candidates_by_chunk_id) != len(cited_ids)
            or set(evidence_by_chunk_id) != cited_ids
        ):
            from app.core.exceptions import AppError

            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理這次產生的引用無法通過來源核對，結果未被採用。請重新提問。",
                502,
            )
        citations = [
            self._citation(
                candidates_by_chunk_id[chunk_id],
                supporting_quote=evidence_by_chunk_id[chunk_id].supporting_quote,
                supported_claim=evidence_by_chunk_id[chunk_id].supported_claim,
            )
            for chunk_id in answer.cited_chunk_ids
        ]
        return KnowledgeAnswerResponse(
            answer_status=(
                KnowledgeAnswerStatus.CLARIFICATION_REQUIRED
                if answer.needs_clarification
                else KnowledgeAnswerStatus.SUPPORTED
            ),
            answer=answer.answer,
            citations=citations,
            unreadable_sources=[self._unreadable_source(item) for item in unreadable_sources],
            generation_mode=provider_name.upper(),
            model_id=model_id,
            clarification_question=answer.clarification_question,
            next_action=(
                "ANSWER_CLARIFICATION_QUESTION"
                if answer.needs_clarification
                else "REVIEW_CITED_SOURCES"
            ),
        )

    @staticmethod
    def _citation(
        item: RetrievedKnowledge,
        *,
        supporting_quote: str | None = None,
        supported_claim: str | None = None,
    ) -> KnowledgeCitation:
        document = item.document
        chunk = item.chunk
        article_no = chunk.article_no
        document_code = str(getattr(document, "document_code", "") or "")
        if document_code.startswith(("LAW-", "REG-")):
            if supporting_quote is not None:
                article_no = _article_no_from_supporting_quote(supporting_quote)
        elif supporting_quote is not None:
            # Manual chunks can contain quoted legal provisions elsewhere on the
            # same page.  Their first detected article number is not the manual's
            # own section identifier, so showing it on the citation card is
            # misleading; page/section metadata remains available instead.
            article_no = None
        return KnowledgeCitation(
            document_id=document.document_id,
            document_title=document.title,
            document_code=document.document_code,
            version_no=document.version_no,
            effective_from=document.effective_from,
            effective_to=document.effective_to,
            chunk_id=chunk.chunk_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_title=chunk.section_title,
            article_no=article_no,
            quoted_text=_excerpt(chunk.content),
            supporting_quote=supporting_quote,
            supported_claim=supported_claim,
        )

    @staticmethod
    def _unreadable_source(item: object) -> KnowledgeUnreadableSource:
        return KnowledgeUnreadableSource(
            document_id=item.document_id,
            document_title=item.document_title,
            original_filename=item.original_filename,
            reason=item.reason,
        )

    def unreadable_answer(self, unreadable_sources: Iterable[object]) -> KnowledgeAnswerResponse:
        sources = [self._unreadable_source(item) for item in unreadable_sources]
        filenames = "、".join(source.original_filename for source in sources)
        return KnowledgeAnswerResponse(
            answer_status=KnowledgeAnswerStatus.NO_RELEVANT_SOURCE,
            citations=[],
            unreadable_sources=sources,
            answer=(
                f"目前沒有可讀取的來源；{filenames} 無法解析，因此 AI 未使用該檔案回答。"
            ),
            generation_mode="SOURCE_READ_ERROR",
            next_action="CHECK_FILE_FORMAT_OR_ENABLE_OCR",
        )
