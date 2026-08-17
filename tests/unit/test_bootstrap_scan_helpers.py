from __future__ import annotations

from reqgraph.cli.commands.bootstrap_scan import _walk_files


def test_walk_files_finds_nested_files_by_suffix(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text("y = 2\n")
    (tmp_path / "c.txt").write_text("not python\n")

    result = set(_walk_files(tmp_path, ".py"))
    assert result == {"a.py", "sub/b.py"}


def test_walk_files_excludes_common_noise_dirs(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    for noisy in (".git", "__pycache__", "node_modules", ".venv"):
        noisy_dir = tmp_path / noisy
        noisy_dir.mkdir()
        (noisy_dir / "ignored.py").write_text("z = 1\n")

    result = set(_walk_files(tmp_path, ".py"))
    assert result == {"a.py"}


def test_walk_files_empty_suffix_returns_all_files(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.json").write_text("{}\n")

    result = set(_walk_files(tmp_path, ""))
    assert result == {"a.py", "b.json"}
