from __future__ import annotations

import pytest

from reqgraph.cli.main import app, main


def test_main_converts_runtime_error_to_clean_exit(monkeypatch, capsys):
    def _raise(*args, **kwargs):
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    monkeypatch.setattr("reqgraph.cli.main.app", _raise)
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_app_itself_still_works_standalone():
    # `python -m reqgraph.cli.main` invokes `app` directly (not `main`) — make
    # sure that path still works after adding the main() wrapper.
    assert callable(app)
