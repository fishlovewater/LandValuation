from __future__ import annotations

import json
import re
from typing import Iterable
from uuid import UUID

import httpx

from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.ai_contract import AiAnswer, build_source_packet, parse_answer
from app.knowledge.service import RetrievedKnowledge


_GENERIC_TERMS = {
    "哪些",
    "相關",
    "規定",
    "什麼",
    "怎麼",
    "如何",
    "請問",
    "目前",
    "辦法",
    "中的",
    "中",
    "是",
    "的",
    "有",
    "要",
    "對",
}

_ARTICLE_PATTERN = re.compile(
    r"第\s*([0-9０-９一二三四五六七八九十百千之\-]+)\s*條"
)
_ARTICLE_HEADER_PATTERN = re.compile(
    r"(?m)^第\s*([0-9０-９一二三四五六七八九十百千之\-]+)\s*條(?:\s|$)"
)
_MAJOR_HEADING_PATTERN = re.compile(
    r"^(?:第[一二三四五六七八九十百千0-9０-９]+[章節篇]|[一二三四五六七八九十]+、)"
)
_OPERATIONAL_TERMS = (
    "怎麼",
    "如何",
    "步驟",
    "流程",
    "操作",
    "填寫",
    "怎樣",
    "要注意",
    "計算方式",
    "查估方式",
)


class OllamaKnowledgeProvider:
    """Use the local model to select evidence, then build a source-exact answer."""

    provider_name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def model_id(self) -> str | None:
        return self.settings.ollama_model

    def configured(self) -> bool:
        return bool(self.settings.ollama_base_url and self.settings.ollama_model)

    async def answer(
        self,
        *,
        question: str,
        candidates: Iterable[RetrievedKnowledge],
    ) -> AiAnswer:
        candidate_list = list(candidates)
        explicitly_named = [
            item
            for item in candidate_list
            if (
                str(getattr(item.document, "title", "") or "").strip()
                and str(getattr(item.document, "title", "") or "").strip() in question
            )
        ]
        if explicitly_named:
            candidate_list = explicitly_named
        packet = build_source_packet(
            candidate_list,
            self.settings.knowledge_ai_max_source_characters,
        )
        packet = self._focus_packet(question, packet)
        if not packet:
            return self._clarification_answer(
                "請確認相關法規、規則或手冊已加入知識庫。"
            )

        output = await self._generate_selection(question, packet)
        try:
            selected_ids, needs_clarification, clarification = self._parse_selection(
                output, packet
            )
        except AppError as exc:
            if exc.code != "AI_PROVIDER_INVALID_RESPONSE":
                raise
            repaired = await self._generate_selection(
                question,
                packet,
                invalid_output=output,
            )
            selected_ids, needs_clarification, clarification = self._parse_selection(
                repaired, packet
            )

        if not selected_ids:
            # The local model can be over-conservative on broad wording such as
            # "有哪些相關規定" even when backend retrieval has already produced
            # topic-matching chunks from the explicitly named official document.
            # In that case, fall back only to the already-authorized/ranked packet;
            # the final answer is still extractive and passes parse_answer().
            selected_ids = self._backend_fallback_ids(question, packet)
            if not selected_ids:
                return self._clarification_answer(
                    clarification or "目前提供的正式來源不足以直接回答這個問題。"
                )
            needs_clarification = False
            clarification = None

        selected_ids = self._filter_selected_ids_by_relevance(
            question,
            packet,
            selected_ids,
        )
        if not selected_ids:
            selected_ids = self._backend_fallback_ids(question, packet)
            needs_clarification = False
            clarification = None
        return self._build_extractive_answer(
            question,
            packet,
            selected_ids,
            needs_clarification=needs_clarification,
            clarification_question=clarification,
        )

    async def _generate_selection(
        self,
        question: str,
        packet: list[dict],
        *,
        invalid_output: str | None = None,
    ) -> str:
        prompt = self._selection_prompt(question, packet)
        if invalid_output:
            prompt += (
                "\n\n前一次輸出格式不合要求。請只修正選擇結果，不要回答問題本身。"
                f"\nINVALID_OUTPUT:\n{invalid_output[:6000]}"
            )
        body = {
            "model": self.settings.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": self._selection_schema(),
            "think": False,
            "options": {"temperature": 0},
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.ollama_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.settings.ollama_base_url}/api/generate",
                    json=body,
                )
        except httpx.RequestError as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "智能助理目前無法連線到本機 AI 服務，請稍後再試。",
                503,
            ) from exc

        if response.status_code == 404:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "目前設定的本機 AI 模型尚未準備完成，請聯絡系統管理者。",
                503,
            )
        try:
            response.raise_for_status()
            payload = response.json()
            return self._clean_json(str(payload["response"]))
        except httpx.HTTPStatusError as exc:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "智能助理目前無法完成回答，請稍後再試。",
                503,
            ) from exc
        except (ValueError, KeyError, TypeError) as exc:
            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理這次沒有產生可採用的來源選擇結果，請重新提問。",
                502,
            ) from exc

    @staticmethod
    def _selection_schema() -> dict:
        return {
            "type": "object",
            "properties": {
                "selected_source_numbers": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 8},
                    "maxItems": 3,
                },
                "needs_clarification": {"type": "boolean"},
                "clarification_question": {"type": ["string", "null"]},
            },
            "required": [
                "selected_source_numbers",
                "needs_clarification",
                "clarification_question",
            ],
            "additionalProperties": False,
        }

    @staticmethod
    def _selection_prompt(question: str, packet: list[dict]) -> str:
        return (
            "你是土地估價知識庫的來源選擇器，不要直接回答使用者問題。\n"
            "SOURCE_PACKET 內的來源依序編號為 1、2、3……。"
            "只可回傳能直接回答 QUESTION 的來源編號，最多 3 個；不要抄寫或生成 chunk_id。\n"
            "優先選擇使用者明確點名的法規或文件，並排除只有關鍵字相似但內容無關的段落。\n"
            "若法律、法規命令與作業手冊都能直接支持同一結論，優先選法律或法規命令；"
            "手冊可用來補充操作細節。\n"
            "不需要一次涵蓋問題的所有面向；只要某個 chunk 對問題提供一項直接、可核對的內容，就應選入。\n"
            "只有所有候選來源都沒有直接相關內容時，selected_source_numbers 才能是空陣列，needs_clarification=true。\n"
            "只輸出符合 JSON schema 的物件，不要 Markdown。\n"
            f"QUESTION:\n{question}\n"
            "SOURCE_PACKET:\n"
            f"{json.dumps([{'source_number': i + 1, **item} for i, item in enumerate(packet)], ensure_ascii=False)}"
        )

    @staticmethod
    def _clean_json(output: str) -> str:
        output = output.strip()
        if output.startswith("```"):
            output = output.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if output.startswith('"'):
            try:
                decoded = json.loads(output)
                if isinstance(decoded, str):
                    output = decoded.strip()
            except json.JSONDecodeError:
                pass
        return output

    @staticmethod
    def _parse_selection(
        output: str, packet: list[dict]
    ) -> tuple[list[UUID], bool, str | None]:
        try:
            parsed = json.loads(output)
            raw_numbers = parsed["selected_source_numbers"]
            source_numbers = [int(value) for value in raw_numbers]
            needs_clarification = bool(parsed["needs_clarification"])
            clarification = parsed["clarification_question"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理這次沒有產生可採用的來源選擇結果，請重新提問。",
                502,
                details={"reason": "MALFORMED_SOURCE_SELECTION"},
            ) from exc

        if any(number < 1 or number > len(packet) for number in source_numbers):
            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理選到不在本次可用來源中的資料，結果未被採用。",
                502,
                details={"reason": "SOURCE_SELECTION_OUTSIDE_ALLOWLIST"},
            )
        deduped: list[UUID] = []
        for number in source_numbers:
            chunk_id = UUID(packet[number - 1]["chunk_id"])
            if chunk_id not in deduped:
                deduped.append(chunk_id)
        deduped = deduped[:3]
        if not deduped and not needs_clarification:
            raise AppError(
                "AI_PROVIDER_INVALID_RESPONSE",
                "智能助理沒有選出足以回答問題的來源。",
                502,
                details={"reason": "EMPTY_SOURCE_SELECTION"},
            )
        return (
            deduped,
            needs_clarification,
            str(clarification).strip() if clarification else None,
        )

    def _build_extractive_answer(
        self,
        question: str,
        packet: list[dict],
        selected_ids: list[UUID],
        *,
        needs_clarification: bool,
        clarification_question: str | None,
    ) -> AiAnswer:
        packet_by_id = {UUID(item["chunk_id"]): item for item in packet}
        evidence: list[dict[str, str]] = []
        lines = ["依目前可核對的正式來源，可確認以下內容："]
        for chunk_id in selected_ids:
            source = packet_by_id[chunk_id]
            quote = self._relevant_quote(
                question,
                str(source["content"]),
                str(source.get("document_title") or ""),
                document_code=str(source.get("document_code") or ""),
            )
            if not quote:
                continue
            index = len(evidence) + 1
            evidence.append(
                {
                    "chunk_id": str(chunk_id),
                    "supporting_quote": quote,
                    "supported_claim": quote,
                }
            )
            lines.append(f"• {quote}【來源{index}】")

        if not evidence:
            # If the model picked an allowed but weak page, recover from the
            # backend-ranked packet instead of falsely claiming there is no
            # source.  These packet entries have already passed document policy
            # and topic ranking, and the quote still has to be an exact substring
            # before parse_answer() accepts it.
            for source in packet[:3]:
                chunk_id = UUID(source["chunk_id"])
                if any(item["chunk_id"] == str(chunk_id) for item in evidence):
                    continue
                quote = self._relevant_quote(
                    question,
                    str(source["content"]),
                    str(source.get("document_title") or ""),
                    document_code=str(source.get("document_code") or ""),
                )
                if not quote:
                    continue
                index = len(evidence) + 1
                evidence.append(
                    {
                        "chunk_id": str(chunk_id),
                        "supporting_quote": quote,
                        "supported_claim": quote,
                    }
                )
                lines.append(f"• {quote}【來源{index}】")
                if len(evidence) >= 3:
                    break

        if not evidence:
            return self._clarification_answer(
                clarification_question or "目前來源與問題的直接關聯仍不足，請再縮小問題範圍。"
            )

        cited_ids = [item["chunk_id"] for item in evidence]
        payload = {
            "answer": "\n".join(lines),
            "cited_chunk_ids": cited_ids,
            "evidence": evidence,
            "needs_clarification": bool(needs_clarification),
            "clarification_question": (
                clarification_question if needs_clarification else None
            ),
        }
        return parse_answer(json.dumps(payload, ensure_ascii=False), packet)

    @staticmethod
    def _relevant_quote(
        question: str,
        content: str,
        document_title: str,
        *,
        document_code: str = "",
        max_chars: int = 520,
    ) -> str | None:
        topic = question
        if document_title and document_title in topic:
            topic = topic.replace(document_title, " ")

        requested_articles = OllamaKnowledgeProvider._article_refs(topic)
        if requested_articles and document_code.startswith(("LAW-", "REG-")):
            block = OllamaKnowledgeProvider._matching_article_block(
                content,
                requested_articles,
            )
            if block:
                return block[:max_chars].strip()

        if "注意" in topic:
            notes = OllamaKnowledgeProvider._notes_span(content, max_chars=max_chars)
            if notes:
                return notes
            return None

        if document_code.startswith(("LAW-", "REG-")):
            article_blocks = OllamaKnowledgeProvider._article_blocks(content)
            if article_blocks:
                scored_blocks = [
                    (
                        OllamaKnowledgeProvider._text_relevance_score(topic, block),
                        -index,
                        block,
                    )
                    for index, block in enumerate(article_blocks)
                ]
                scored_blocks = [item for item in scored_blocks if item[0] > 0]
                if scored_blocks:
                    scored_blocks.sort(reverse=True)
                    return scored_blocks[0][2][:max_chars].strip()

        segments = [
            segment.strip()
            for segment in re.split(r"(?<=[。！？；])|\n+", content)
            if segment.strip()
        ]
        scored: list[tuple[int, int, int, str]] = []
        for start in range(len(segments)):
            for width in (1, 2, 3):
                window_segments = segments[start : start + width]
                if len(window_segments) != width:
                    continue
                window = "\n".join(window_segments).strip()
                score = OllamaKnowledgeProvider._text_relevance_score(topic, window)
                if width == 1 and OllamaKnowledgeProvider._is_heading_only(window):
                    score -= 120
                if score > 0:
                    scored.append((score, -width, -start, window))
        if not scored:
            return None
        scored.sort(reverse=True)
        quote = scored[0][3]
        if len(quote) < 8:
            return None
        return quote[:max_chars].strip()

    @staticmethod
    def _focus_packet(question: str, packet: list[dict]) -> list[dict]:
        if not packet:
            return []
        scored = [
            (OllamaKnowledgeProvider._chunk_relevance_score(question, item), -index, item)
            for index, item in enumerate(packet)
        ]
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        positive = [item for score, _, item in scored if score > 0]
        return positive[:8] if positive else packet[:8]

    @staticmethod
    def _filter_selected_ids_by_relevance(
        question: str,
        packet: list[dict],
        selected_ids: list[UUID],
    ) -> list[UUID]:
        if not selected_ids:
            return []
        scores = {
            UUID(item["chunk_id"]): OllamaKnowledgeProvider._direct_relevance_score(
                question, item
            )
            for item in packet
        }
        max_score = max(scores.values(), default=0)
        if max_score <= 0:
            return []
        operational = OllamaKnowledgeProvider._is_operational_question(question)
        threshold_ratio = 0.9 if operational else 0.65
        # Qwen may return several loosely related sources. Keep only sources
        # whose direct relevance is close to the best backend-ranked evidence;
        # operational questions are intentionally stricter because practical
        # manuals often contain one clearly best procedure/span.
        threshold = max(1, int(max_score * threshold_ratio))
        filtered = [
            chunk_id
            for chunk_id in selected_ids
            if scores.get(chunk_id, 0) >= threshold
        ][:3]
        if not filtered:
            return []

        packet_by_id = {UUID(item["chunk_id"]): item for item in packet}
        total_scores = {
            UUID(item["chunk_id"]): OllamaKnowledgeProvider._chunk_relevance_score(
                question, item
            )
            for item in packet
        }
        if operational:
            # Direct relevance already controls operational questions. Do not let
            # a legal-authority bonus displace a substantially clearer procedure.
            return filtered

        best_total = max(total_scores.values(), default=0)
        best_selected_total = max(total_scores.get(chunk_id, 0) for chunk_id in filtered)
        if best_total > 0 and best_selected_total < best_total * 0.65:
            return []

        authoritative = [
            chunk_id
            for chunk_id in filtered
            if str(packet_by_id[chunk_id].get("document_code") or "").startswith(
                ("LAW-", "REG-")
            )
        ]
        if authoritative:
            best_authoritative = max(scores[chunk_id] for chunk_id in authoritative)
            # Prefer primary legal sources when they are almost as directly
            # relevant as the strongest candidate. Manuals remain eligible when
            # they contain materially more direct operational content.
            if best_authoritative >= max_score * 0.8:
                return authoritative[:3]
        return filtered

    @staticmethod
    def _backend_fallback_ids(question: str, packet: list[dict]) -> list[UUID]:
        if not packet:
            return []
        operational = OllamaKnowledgeProvider._is_operational_question(question)
        scorer = (
            OllamaKnowledgeProvider._direct_relevance_score
            if operational
            else OllamaKnowledgeProvider._chunk_relevance_score
        )
        scored = [
            (
                scorer(question, item),
                -index,
                UUID(item["chunk_id"]),
            )
            for index, item in enumerate(packet)
        ]
        scored.sort(reverse=True)
        max_score = scored[0][0]
        if max_score <= 0:
            return []
        # A fallback exists only for malformed/over-conservative model selection;
        # returning the single strongest backend-ranked source is safer than
        # padding the answer with additional merely-related citations.
        return [scored[0][2]]

    @staticmethod
    def _is_operational_question(question: str) -> bool:
        compact = "".join(question.split())
        return any(term in compact for term in _OPERATIONAL_TERMS)

    @staticmethod
    def _chunk_relevance_score(question: str, source: dict) -> int:
        score = OllamaKnowledgeProvider._direct_relevance_score(question, source)
        if score < 0:
            return score
        document_code = str(source.get("document_code") or "")
        if document_code.startswith("LAW-"):
            score += 500
        elif document_code.startswith("REG-"):
            score += 450
        return score

    @staticmethod
    def _direct_relevance_score(question: str, source: dict) -> int:
        title = str(source.get("document_title") or "").strip()
        topic = question.replace(title, " ") if title and title in question else question
        content = str(source.get("content") or "")
        requested_articles = OllamaKnowledgeProvider._article_refs(topic)
        if requested_articles and str(source.get("document_code") or "").startswith(
            ("LAW-", "REG-")
        ):
            if OllamaKnowledgeProvider._matching_article_block(
                content,
                requested_articles,
            ):
                return 10_000 + OllamaKnowledgeProvider._text_relevance_score(
                    topic, content
                )
            return -10_000
        score = OllamaKnowledgeProvider._text_relevance_score(topic, content)
        compact_head = re.sub(r"\s+", "", content[:240].lower())
        for phrase, weight in OllamaKnowledgeProvider._weighted_phrases(
            re.sub(r"\s+", "", topic.lower())
        )[:12]:
            if len(phrase) >= 4 and phrase in compact_head:
                score += weight * 4
        return score

    @staticmethod
    def _text_relevance_score(question: str, text: str) -> int:
        normalized_question = re.sub(r"\s+", "", question.lower())
        normalized_text = re.sub(r"\s+", "", text.lower())
        score = 0
        for phrase, weight in OllamaKnowledgeProvider._weighted_phrases(
            normalized_question
        ):
            occurrences = normalized_text.count(phrase)
            if occurrences:
                score += weight * min(occurrences, 3)
        return score

    @staticmethod
    def _weighted_phrases(question: str) -> list[tuple[str, int]]:
        latin = re.findall(r"[a-z0-9_]{2,}", question)
        chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", question)
        phrases: dict[str, int] = {}
        for token in latin:
            phrases[token] = max(phrases.get(token, 0), len(token) * len(token))
        for run in chinese_runs:
            for width in range(min(8, len(run)), 1, -1):
                for index in range(len(run) - width + 1):
                    token = run[index : index + width]
                    if token in _GENERIC_TERMS:
                        continue
                    phrases[token] = max(
                        phrases.get(token, 0),
                        width * width,
                    )
        return sorted(
            phrases.items(),
            key=lambda item: (item[1], len(item[0])),
            reverse=True,
        )

    @staticmethod
    def _article_refs(text: str) -> set[str]:
        refs: set[str] = set()
        for match in _ARTICLE_PATTERN.finditer(text):
            raw = match.group(1).replace(" ", "")
            refs.add(OllamaKnowledgeProvider._canonical_article_number(raw))
        return refs

    @staticmethod
    def _canonical_article_number(raw: str) -> str:
        raw = raw.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        if re.fullmatch(r"[0-9]+(?:-[0-9]+)?", raw):
            return raw
        if "之" in raw:
            base, sub = raw.split("之", 1)
            base_no = OllamaKnowledgeProvider._chinese_number(base)
            sub_no = OllamaKnowledgeProvider._chinese_number(sub)
            if base_no is not None and sub_no is not None:
                return f"{base_no}-{sub_no}"
        number = OllamaKnowledgeProvider._chinese_number(raw)
        return str(number) if number is not None else raw

    @staticmethod
    def _chinese_number(raw: str) -> int | None:
        digits = {
            "零": 0,
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if not raw:
            return None
        if all(char in digits for char in raw):
            value = 0
            for char in raw:
                value = value * 10 + digits[char]
            return value
        if "百" in raw:
            left, right = raw.split("百", 1)
            hundreds = digits.get(left, 1) if left else 1
            remainder = OllamaKnowledgeProvider._chinese_number(right) if right else 0
            return hundreds * 100 + (remainder or 0)
        if "十" in raw:
            left, right = raw.split("十", 1)
            tens = digits.get(left, 1) if left else 1
            ones = digits.get(right, 0) if right else 0
            return tens * 10 + ones
        return digits.get(raw)

    @staticmethod
    def _article_blocks(content: str) -> list[str]:
        matches = list(_ARTICLE_HEADER_PATTERN.finditer(content))
        if not matches:
            return []
        blocks: list[str] = []
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            block = content[match.start() : end].strip()
            if block:
                blocks.append(block)
        return blocks

    @staticmethod
    def _matching_article_block(content: str, requested_articles: set[str]) -> str | None:
        for block in OllamaKnowledgeProvider._article_blocks(content):
            header = _ARTICLE_HEADER_PATTERN.match(block)
            if not header:
                continue
            article_no = OllamaKnowledgeProvider._canonical_article_number(
                header.group(1).replace(" ", "")
            )
            if article_no in requested_articles:
                return block
        return None

    @staticmethod
    def _notes_span(content: str, *, max_chars: int) -> str | None:
        match = re.search(r"(?:二[、.．]?\s*)?注意事項\s*[:：]?", content)
        if not match:
            return None
        tail = content[match.start() :]
        next_section = re.search(r"\n\s*(?:三|四|五|六|七|八|九|十)[、.．]", tail[1:])
        if next_section:
            tail = tail[: next_section.start() + 1]
        tail = tail.strip()
        if len(tail) < 12:
            return None
        return tail[:max_chars].strip()

    @staticmethod
    def _is_heading_only(text: str) -> bool:
        compact = "".join(text.split())
        if len(compact) > 34:
            return False
        if _MAJOR_HEADING_PATTERN.match(compact):
            return True
        return compact.endswith(("表", "章", "節", "說明", "注意事項")) and not re.search(
            r"[。；:：]", compact
        )

    @staticmethod
    def _terms(question: str) -> set[str]:
        normalized = question.lower().strip()
        latin = set(re.findall(r"[a-z0-9_]{2,}", normalized))
        chinese_runs = re.findall(r"[\u4e00-\u9fff]{2,}", normalized)
        bigrams = {
            run[index : index + 2]
            for run in chinese_runs
            for index in range(len(run) - 1)
        }
        return {term for term in latin | bigrams if term not in _GENERIC_TERMS}

    @staticmethod
    def _clarification_answer(question: str) -> AiAnswer:
        return AiAnswer(
            answer="目前提供的正式來源不足以直接確認這個問題。",
            cited_chunk_ids=[],
            evidence=[],
            needs_clarification=True,
            clarification_question=question,
        )