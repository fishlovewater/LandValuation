from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pypdf.errors import PdfReadError

from app.core.exceptions import AppError


logger = logging.getLogger(__name__)
T = TypeVar("T")


def build_pdf_safely(
    builder: Callable[..., T],
    *args: Any,
    source_is_user_upload: bool = False,
    **kwargs: Any,
) -> T:
    """Convert PDF-library failures into stable, user-safe API errors."""
    try:
        return builder(*args, **kwargs)
    except AppError:
        raise
    except FileNotFoundError as exc:
        logger.exception("PDF template file is missing")
        raise AppError(
            "PDF_TEMPLATE_MISSING",
            "找不到 PDF 版型檔，請通知系統管理者確認部署內容",
            500,
        ) from exc
    except PdfReadError as exc:
        logger.exception("PDF input or template cannot be parsed")
        if source_is_user_upload:
            raise AppError(
                "PDF_SOURCE_INVALID",
                "上傳的 PDF 已損壞、加密或格式無法讀取",
                422,
            ) from exc
        raise AppError(
            "PDF_TEMPLATE_INVALID",
            "PDF 版型損壞或格式無法讀取，請通知系統管理者",
            500,
        ) from exc
    except PermissionError as exc:
        logger.exception("PDF file permission error")
        raise AppError(
            "PDF_FILE_ACCESS_FAILED",
            "系統無法讀取 PDF 版型或暫存檔",
            500,
        ) from exc
    except OSError as exc:
        logger.exception("PDF file IO failed")
        raise AppError(
            "PDF_FILE_IO_FAILED",
            "PDF 檔案讀寫失敗，請稍後再試",
            500,
        ) from exc
    except RuntimeError as exc:
        logger.exception("PDF builder validation failed")
        message = str(exc)
        if "缺少" in message:
            raise AppError(
                "PDF_REQUIRED_DATA_MISSING",
                message,
                422,
            ) from exc
        if any(keyword in message for keyword in ("頁數", "A4", "版型")):
            raise AppError(
                "PDF_OUTPUT_VALIDATION_FAILED",
                "PDF 產生後的頁數或版面驗證失敗",
                500,
            ) from exc
        raise AppError(
            "PDF_GENERATION_FAILED",
            "PDF 產生失敗，請確認輸入資料與版型內容",
            500,
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
        logger.exception("PDF builder input is invalid")
        raise AppError(
            "PDF_INPUT_INVALID",
            "PDF 輸入資料格式錯誤或缺少必要欄位",
            422,
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected PDF generation failure")
        raise AppError(
            "PDF_GENERATION_FAILED",
            "PDF 產生失敗，請稍後再試；若持續發生請聯絡系統管理者",
            500,
        ) from exc
