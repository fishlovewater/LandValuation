"""Start the API on Windows without psycopg's ProactorEventLoop conflict.

Use this entry point for local Windows testing instead of ``python -m uvicorn``.
The Docker deployment runs on Linux and is not affected.
"""

import asyncio
import os
import sys
from pathlib import Path


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    project_root = str(Path(__file__).resolve().parents[1])
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "8002")),
        # Uvicorn's Windows "auto" loop factory selects ProactorEventLoop.
        # Keep the selector policy configured above for psycopg async support.
        loop="none",
    )


if __name__ == "__main__":
    main()
