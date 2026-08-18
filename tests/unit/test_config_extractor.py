from __future__ import annotations

from reqgraph.extract.config_extractor import extract_config_units, is_config_path


def test_env_file_extraction():
    units = extract_config_units(".env", "FOO_ENABLED=true\nBAR=1\n# comment\n\n")
    keys = {u.key: u.kind for u in units}
    assert keys == {"FOO_ENABLED": "feature_flag", "BAR": "environment"}


def test_toml_extraction_flattens_nested_keys():
    units = extract_config_units("pyproject.toml", '[project]\nname = "demo"\n\n[tool.x]\nflag = true\n')
    keys = {u.key for u in units}
    assert "project.name" in keys
    assert "tool.x.flag" in keys


def test_python_settings_extraction_only_top_level_uppercase_literals():
    source = "DEBUG = True\nFEATURE_X_ENABLED = False\nlower_case = 1\n\ndef f():\n    LOCAL = 2\n"
    units = extract_config_units("settings.py", source)
    keys = {u.key: u.kind for u in units}
    assert keys == {"DEBUG": "setting", "FEATURE_X_ENABLED": "feature_flag"}


def test_config_diff_is_key_level_not_file_level():
    source_a = "DEBUG = True\nFEATURE_X_ENABLED = False\n"
    source_b = "DEBUG = True\nFEATURE_X_ENABLED = True\n"
    units_a = {u.key: u.value_hash for u in extract_config_units("settings.py", source_a)}
    units_b = {u.key: u.value_hash for u in extract_config_units("settings.py", source_b)}
    assert units_a["DEBUG"] == units_b["DEBUG"]
    assert units_a["FEATURE_X_ENABLED"] != units_b["FEATURE_X_ENABLED"]


def test_lockfiles_excluded_by_default():
    assert is_config_path("package-lock.json") is False
    assert is_config_path("pnpm-lock.yaml") is False
    assert is_config_path("nested/dir/package-lock.json") is False


def test_lockfiles_included_when_opted_in():
    assert is_config_path("package-lock.json", include_lockfiles=True) is True
    assert is_config_path("pnpm-lock.yaml", include_lockfiles=True) is True


def test_manifest_and_project_config_always_included():
    assert is_config_path("package.json") is True
    assert is_config_path("public/manifest.json") is True
    assert is_config_path("tsconfig.json") is True
    assert is_config_path(".oxlintrc.json") is True
