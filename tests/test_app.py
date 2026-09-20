"""Headless Streamlit smoke test."""

from streamlit.testing.v1 import AppTest


def test_app_starts_without_exception() -> None:
    app = AppTest.from_file("../app.py", default_timeout=10).run()
    assert not app.exception
    assert app.slider[0].value == 0.01
    assert app.number_input[0].value == 3
    assert app.checkbox[0].value is False
    assert [tab.label for tab in app.tabs] == [
        "Health",
        "Upload",
        "Line items",
        "Checks",
        "Retry log",
        "Export",
    ]
    assert all(metric.value in {"Yes", "No"} for metric in app.metric)
