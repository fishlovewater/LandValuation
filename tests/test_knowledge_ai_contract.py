import json
from uuid import uuid4

import pytest

from app.core.exceptions import AppError
from app.knowledge.ai_contract import parse_answer


def test_parse_answer_rejects_cited_clarification_without_display_marker():
    chunk_id = uuid4()
    packet = [
        {
            "chunk_id": str(chunk_id),
            "content": "市價查估應依明確法源辦理。",
        }
    ]

    with pytest.raises(AppError) as raised:
        parse_answer(
            json.dumps(
                {
                    "answer": "目前提供的來源指出：市價查估應依明確法源辦理。適用年度仍不明。",
                    "cited_chunk_ids": [str(chunk_id)],
                    "evidence": [
                        {
                            "chunk_id": str(chunk_id),
                            "supporting_quote": "市價查估應依明確法源辦理。",
                            "supported_claim": "市價查估應依明確法源辦理。",
                        }
                    ],
                    "needs_clarification": True,
                    "clarification_question": "請提供適用年度。",
                },
                ensure_ascii=False,
            ),
            packet,
        )

    assert raised.value.details["validation_errors"] == ["CITATION_MARKER_MISSING"]


def test_parse_answer_accepts_cited_clarification_with_display_marker():
    chunk_id = uuid4()
    packet = [
        {
            "chunk_id": str(chunk_id),
            "content": "市價查估應依明確法源辦理。",
        }
    ]

    answer = parse_answer(
        json.dumps(
            {
                "answer": "目前來源指出市價查估應依明確法源辦理。【來源1】適用年度仍不明。",
                "cited_chunk_ids": [str(chunk_id)],
                "evidence": [
                    {
                        "chunk_id": str(chunk_id),
                        "supporting_quote": "市價查估應依明確法源辦理。",
                        "supported_claim": "市價查估應依明確法源辦理。",
                    }
                ],
                "needs_clarification": True,
                "clarification_question": "請提供適用年度。",
            },
            ensure_ascii=False,
        ),
        packet,
    )

    assert answer.needs_clarification is True
    assert answer.cited_chunk_ids == [chunk_id]


def test_parse_answer_rejects_quote_that_only_matches_after_joining_paragraphs():
    chunk_id = uuid4()
    packet = [
        {
            "chunk_id": str(chunk_id),
            "content": "第一段結論。\n\n第二段補充。",
        }
    ]

    with pytest.raises(AppError) as raised:
        parse_answer(
            json.dumps(
                {
                    "answer": "第一段結論。第二段補充。【來源1】",
                    "cited_chunk_ids": [str(chunk_id)],
                    "evidence": [
                        {
                            "chunk_id": str(chunk_id),
                            "supporting_quote": "第一段結論。第二段補充。",
                            "supported_claim": "第一段結論。第二段補充。",
                        }
                    ],
                    "needs_clarification": False,
                    "clarification_question": None,
                },
                ensure_ascii=False,
            ),
            packet,
        )

    assert raised.value.details["validation_errors"] == [
        "EVIDENCE_QUOTE_NOT_VERIFIABLE_IN_SOURCE"
    ]


def test_parse_answer_allows_crlf_to_lf_line_ending_normalisation():
    chunk_id = uuid4()
    packet = [
        {
            "chunk_id": str(chunk_id),
            "content": "第一行\r\n第二行。",
        }
    ]

    answer = parse_answer(
        json.dumps(
            {
                "answer": "第一行\n第二行。【來源1】",
                "cited_chunk_ids": [str(chunk_id)],
                "evidence": [
                    {
                        "chunk_id": str(chunk_id),
                        "supporting_quote": "第一行\n第二行。",
                        "supported_claim": "第一行\n第二行。",
                    }
                ],
                "needs_clarification": False,
                "clarification_question": None,
            },
            ensure_ascii=False,
        ),
        packet,
    )

    assert answer.evidence[0].supporting_quote == "第一行\n第二行。"


def test_parse_answer_allows_pdf_line_wrap_to_be_returned_as_space():
    chunk_id = uuid4()
    packet = [
        {
            "chunk_id": str(chunk_id),
            "content": "比準地指地價區段內具代表性，\n以作為各宗土地市價比較基準之宗地。",
        }
    ]

    answer = parse_answer(
        json.dumps(
            {
                "answer": "比準地指地價區段內具代表性， 以作為各宗土地市價比較基準之宗地。【來源1】",
                "cited_chunk_ids": [str(chunk_id)],
                "evidence": [
                    {
                        "chunk_id": str(chunk_id),
                        "supporting_quote": "比準地指地價區段內具代表性， 以作為各宗土地市價比較基準之宗地。",
                        "supported_claim": "比準地指地價區段內具代表性， 以作為各宗土地市價比較基準之宗地。",
                    }
                ],
                "needs_clarification": False,
                "clarification_question": None,
            },
            ensure_ascii=False,
        ),
        packet,
    )

    assert answer.cited_chunk_ids == [chunk_id]


def test_parse_answer_reduces_unmatched_long_quote_to_verified_claim():
    chunk_id = uuid4()
    source_claim = "比準地指地價區段內具代表性之宗地。"
    packet = [{"chunk_id": str(chunk_id), "content": source_claim}]

    answer = parse_answer(
        json.dumps(
            {
                "answer": f"{source_claim}【來源1】",
                "cited_chunk_ids": [str(chunk_id)],
                "evidence": [
                    {
                        "chunk_id": str(chunk_id),
                        "supporting_quote": f"依規定，{source_claim}",
                        "supported_claim": source_claim,
                    }
                ],
                "needs_clarification": False,
                "clarification_question": None,
            },
            ensure_ascii=False,
        ),
        packet,
    )

    assert answer.evidence[0].supporting_quote == source_claim
