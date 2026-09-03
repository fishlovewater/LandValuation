import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_review_model_alone_can_construct_with_submission_relationship():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.review.models import Review; "
                "review = Review(); "
                "assert review.latest_submission is None; "
                "print('ok')"
            ),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
