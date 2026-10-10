"""Regression coverage for Wingman v3 custom-skill discovery."""

import importlib.util
from pathlib import Path
import sys
import types

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_declares_current_api_and_conventional_entrypoint():
    config = yaml.safe_load((ROOT / "default_config.yaml").read_text(encoding="utf-8"))
    assert config.get("api_version") == 3
    assert config["module"] == "skills.sc_accountant.main"
    assert config["name"] == "SC_Accountant"
    assert config["auto_activate"] is True


def test_custom_loader_imports_erp_without_runtime_setup_or_path_pollution(monkeypatch):
    # Wingman 3.2.2 loads main.py through spec_from_file_location, without a package.
    host = types.ModuleType("skills.skill_base")

    class Skill:
        def __init__(self, *args, **kwargs):
            raise AssertionError("Import probing must not instantiate the skill")

    def tool(**kwargs):
        def decorate(fn):
            return fn

        return decorate

    host.Skill, host.tool = Skill, tool
    monkeypatch.setitem(sys.modules, "skills.skill_base", host)
    before = list(sys.path)
    spec = importlib.util.spec_from_file_location(
        "accountant_host_probe", ROOT / "main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cls = module.SC_Accountant
    assert issubclass(cls, Skill)
    assert all(
        hasattr(cls, name) for name in ("erp_report", "erp_record", "erp_dashboard")
    )
    assert sys.path == before
