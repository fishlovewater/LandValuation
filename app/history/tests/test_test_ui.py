from pathlib import Path


def test_manual_ui_exercises_history_contract():
    html = (Path(__file__).parents[1] / "test_ui" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "/history/cases" in html
    assert "/history/documents/" in html
    assert "Authorization" in html
    assert "risk_level" in html


def test_manual_ui_contains_new_taipei_district_mapping():
    html = (Path(__file__).parents[1] / "test_ui" / "index.html").read_text(
        encoding="utf-8"
    )
    assert '<option value="31">新北市</option>' in html
    assert "['3101','板橋區']" in html
    assert "['3129','烏來區']" in html
    assert html.count("['31") == 29


def test_manual_ui_renders_dynamic_search_values_without_inner_html():
    html = (Path(__file__).parents[1] / "test_ui" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "innerHTML" not in html
    assert "textContent" in html
