from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

from app.core.config import Settings
from app.core.exceptions import AppError
from app.knowledge.ai_contract import (
    AiAnswer,
    answer_output_schema,
    answer_prompt,
    build_source_packet,
    parse_answer,
    source_grounding_instructions,
)
from app.knowledge.service import RetrievedKnowledge


_CODEX_ENV_KEYS = frozenset(
    {
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "SYSTEMDRIVE",
        "TEMP",
        "TMP",
        "TMPDIR",
        "HOME",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "APPDATA",
        "LOCALAPPDATA",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "CODEX_HOME",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "TERM",
        "TERM_PROGRAM",
        "LANG",
        "LC_ALL",
        "NO_COLOR",
    }
)


class CodexCliKnowledgeProvider:
    """Development-only adapter for a locally authenticated Codex CLI."""

    provider_name = "codex_cli"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def executable_found(self) -> bool:
        return shutil.which(self.settings.codex_cli_command) is not None

    @property
    def model_id(self) -> str | None:
        return self.settings.codex_cli_model or "codex-cli-default"

    async def answer(
        self,
        *,
        question: str,
        candidates: Iterable[RetrievedKnowledge],
    ) -> AiAnswer:
        packet = self._source_packet(candidates)
        if not packet:
            return AiAnswer(
                answer="目前沒有可提供給 AI 分析的已發布且已擷取來源。",
                cited_chunk_ids=[],
                evidence=[],
                needs_clarification=True,
                clarification_question="請先確認相關法規、規則或手冊已完成擷取並發布。",
            )
        executable = shutil.which(self.settings.codex_cli_command)
        if executable is None:
            raise AppError(
                "AI_PROVIDER_UNAVAILABLE",
                "找不到 Codex CLI；請在執行 API 的主機安裝並登入 Codex。",
                503,
            )

        schema_path: Path | None = None
        workdir: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", encoding="utf-8", delete=False
            ) as schema_file:
                import json

                json.dump(answer_output_schema(), schema_file, ensure_ascii=False)
                schema_path = Path(schema_file.name)
            workdir = tempfile.mkdtemp(prefix="knowledge-codex-")
            command = [
                executable,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--ask-for-approval",
                "never",
                "--sandbox",
                "read-only",
                "-c",
                'web_search="disabled"',
                "-c",
                "features.shell_tool=false",
                "-c",
                "features.apps=false",
                "-c",
                "features.multi_agent=false",
                "-c",
                "agents.enabled=false",
                "-c",
                "allow_login_shell=false",
                "--skip-git-repo-check",
                "--output-schema",
                str(schema_path),
            ]
            if self.settings.codex_cli_model:
                command.extend(["--model", self.settings.codex_cli_model])
            command.extend(
                [
                    "-C",
                    workdir,
                    (
                        f"{source_grounding_instructions()}\n"
                        "Answer the user's question using only the source packet provided on stdin. "
                        "Do not execute commands, access files, browse, use web search, or use outside knowledge. "
                        "Return the required JSON only."
                    ),
                ]
            )
            prompt_bytes = answer_prompt(question, packet).encode("utf-8")

            def run_codex() -> subprocess.CompletedProcess[bytes]:
                # Windows SelectorEventLoop is required by this project for
                # psycopg compatibility, but it does not implement asyncio
                # subprocess transports. Run the blocking CLI in a worker
                # thread instead; subprocess.run enforces the same timeout and
                # kills the child if it expires.
                return subprocess.run(
                    command,
                    input=prompt_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=workdir,
                    timeout=self.settings.codex_cli_timeout_seconds,
                    check=False,
                    env=self._subprocess_environment(),
                )
            try:
                process = await asyncio.to_thread(run_codex)
            except subprocess.TimeoutExpired:
                raise AppError("AI_PROVIDER_TIMEOUT", "Codex 分析逾時，請稍後再試。", 504)
            except OSError as exc:
                raise AppError(
                    "AI_PROVIDER_UNAVAILABLE",
                    "無法啟動 Codex CLI；請確認執行檔路徑與 Windows 權限。",
                    503,
                ) from exc
            if process.returncode != 0:
                stderr_text = process.stderr.decode("utf-8", "replace")[-1000:]
                if "Could not find home directory" in stderr_text:
                    raise AppError(
                        "AI_PROVIDER_ENVIRONMENT_ERROR",
                        "Codex CLI 在 API 子程序中找不到使用者主目錄，無法讀取既有登入狀態。"
                        "請在執行 API 的 Windows 使用者環境確認 Codex CLI 可正常執行並完成登入後，再重啟 API。",
                        503,
                        details={
                            "reason": "CODEX_HOME_DIRECTORY_UNAVAILABLE",
                            "stderr": stderr_text,
                        },
                    )
                raise AppError(
                    "AI_PROVIDER_UNAVAILABLE",
                    "Codex 無法完成分析；請確認 API 主機的網路與 Codex 登入狀態。",
                    503,
                    details={
                        "exit_code": process.returncode,
                        "stderr": stderr_text,
                    },
                )
            return parse_answer(process.stdout.decode("utf-8", "replace"), packet)
        finally:
            if schema_path is not None:
                schema_path.unlink(missing_ok=True)
            if workdir is not None:
                shutil.rmtree(workdir, ignore_errors=True)

    def _source_packet(self, candidates: Iterable[RetrievedKnowledge]) -> list[dict]:
        """Pass all authorized sources in database order; no Chinese keyword scoring occurs here."""
        return build_source_packet(candidates, self.settings.knowledge_ai_max_source_characters)

    @staticmethod
    def _subprocess_environment() -> dict[str, str]:
        """Pass only process/runtime, home, and Codex authentication settings."""

        return {
            key: value
            for key, value in os.environ.items()
            if key.upper() in _CODEX_ENV_KEYS
        }

    @staticmethod
    def _parse_answer(output: str, packet: list[dict]) -> AiAnswer:
        """Compatibility wrapper for provider-level contract tests."""

        return parse_answer(output, packet)
