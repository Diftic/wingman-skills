"""Wingman boundary tests with a minimal host double (no audio/network runtime)."""

import asyncio
import importlib
import json
import sys
import threading
import types
from pathlib import Path

import pytest


@pytest.fixture
def adapter(monkeypatch):
    host = types.ModuleType("skills.skill_base")

    class Skill:
        def __init__(self, config, settings=None, wingman=None):
            self.config = config
            self.wingman = wingman
            self.name = "SC_Accountant"
            self.log = types.SimpleNamespace(warning=lambda *a, **k: None)

        async def prepare(self):
            pass

        async def unload(self):
            pass

        async def validate(self):
            return []

        def retrieve_custom_property_value(self, key, errors):
            return self.config.get(key)

        def get_generated_files_dir(self):
            return self.config["data_dir"]

    def tool(**options):
        def decorate(fn):
            fn.tool_options = options
            return fn

        return decorate

    host.Skill, host.tool = Skill, tool
    monkeypatch.setitem(sys.modules, "skills.skill_base", host)
    sys.modules.pop("skills.sc_accountant.erp_skill", None)
    from skills.sc_accountant import erp_web
    class PreviewServer:
        url = "http://127.0.0.1:7863"
        lan_url = "http://192.168.1.20:7863/?share=test"
        def __init__(self, *args, **kwargs): pass
        def start(self): return self.url
        def stop(self): pass
    monkeypatch.setattr(erp_web, "ERPServer", PreviewServer)
    return importlib.import_module("skills.sc_accountant.erp_skill")


def test_three_tools_only_and_manual_mode_missing_feed(adapter, tmp_path):
    skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
    tools = [
        name
        for name, value in vars(type(skill)).items()
        if hasattr(value, "tool_options")
    ]
    assert sorted(tools) == ["erp_dashboard", "erp_record", "erp_report"]
    assert skill._reader_path() is None
    assert "manual" in skill._feed_status.lower()


def test_bounded_report_preserves_valid_json_and_indicates_omissions(adapter):
    report = {
        "mode": "simple",
        "data": {"rows": [{"note": "x" * 10000} for _ in range(100)]},
    }
    text = adapter.compact_report(report)
    assert len(text) <= 3500
    parsed = json.loads(text)
    assert parsed["truncated"] is True
    assert "dashboard" in parsed["hint"].lower()


def test_invalid_record_never_calls_engine(adapter, tmp_path):
    class Never:
        def command(self, *args):
            raise AssertionError("must not mutate")

    skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
    skill._engine = Never()
    for details in ("{bad", "[]", "null", "42"):
        result = json.loads(asyncio.run(skill.erp_record("cash", details)))
        assert "error" in result


def test_unload_waits_for_cancelled_poll_worker_before_closing(adapter, tmp_path):
    entered, release = threading.Event(), threading.Event()
    order = []

    class Engine:
        def close(self):
            order.append("closed")

    def slow_import():
        entered.set()
        release.wait(timeout=5)
        order.append("imported")

    async def run():
        skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
        skill._engine = Engine()
        skill._poll_task = asyncio.create_task(skill._worker(slow_import))
        await asyncio.to_thread(entered.wait, 2)
        unloading = asyncio.create_task(skill.unload())
        await asyncio.sleep(0.03)
        assert "closed" not in order
        release.set()
        await unloading
        assert order == ["imported", "closed"]

    asyncio.run(run())


def test_legacy_import_cannot_read_arbitrary_folders(adapter, tmp_path):
    class Never:
        def command(self, *args):
            raise AssertionError("must not read outside own generated folder")

    skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
    skill._engine = Never()
    result = asyncio.run(
        skill.erp_record("import_legacy", json.dumps({"path": str(tmp_path.parent)}))
    )
    assert "error" in json.loads(result)


def test_cancelled_prepare_closes_engine_created_by_background_worker(
    adapter, monkeypatch, tmp_path
):
    from skills.sc_accountant import erp

    entered, release = threading.Event(), threading.Event()
    order = []

    class Engine:
        def __init__(self, path):
            entered.set()
            release.wait(timeout=5)
            order.append("created")

        def close(self):
            order.append("closed")

    monkeypatch.setattr(erp, "ERP", Engine)

    async def run():
        skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
        preparing = asyncio.create_task(skill.prepare())
        assert await asyncio.to_thread(entered.wait, 2)
        preparing.cancel()
        await asyncio.sleep(0.03)
        assert "closed" not in order
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await preparing
        assert order == ["created", "closed"]
        assert skill._engine is None

    asyncio.run(run())


def test_real_engine_mode_persists_and_all_actions_are_discoverable(adapter, tmp_path):
    config = {
        "data_dir": str(tmp_path),
        "complexity_layer": "simple",
        "auto_sync_interval": 0,
    }

    async def run():
        skill = adapter.SC_Accountant(config)
        await skill.prepare()
        try:
            result = json.loads(
                await skill.erp_record("set_mode", '{"mode":"advanced"}')
            )
            assert "error" not in result
            assert json.loads(await skill.erp_report())["mode"] == "advanced"
            help_result = json.loads(await skill.erp_report("help"))
            names = " ".join(help_result["actions"].values())
            assert all(name in names for name in skill._engine.HELP)
            assert "error" not in json.loads(await skill.erp_report("help:record_cash"))
            for alias in ("jobs", "finance", "planning"):
                assert "error" not in json.loads(await skill.erp_report(alias))
        finally:
            await skill.unload()
        skill = adapter.SC_Accountant(config)
        await skill.prepare()
        try:
            assert json.loads(await skill.erp_report())["mode"] == "advanced"
            config["complexity_layer"] = "advanced"
            await skill.erp_report()
            config["complexity_layer"] = "simple"
            assert json.loads(await skill.erp_report())["mode"] == "simple"
        finally:
            await skill.unload()

    asyncio.run(run())


def test_standalone_import_does_not_load_wingman_or_reader_host():
    import subprocess

    root = Path(__file__).resolve().parents[3]
    script = (
        "import sys; before=list(sys.path); "
        "from skills.sc_accountant.erp import ERP; "
        "from skills.sc_accountant.erp_feed import capture_once; "
        "assert before == sys.path; "
        "assert 'skills.skill_base' not in sys.modules; "
        "assert 'skills.sc_log_reader' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=root, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_bundled_client_matches_public_reader_contract():
    skill = Path(__file__).resolve().parents[1]
    assert (skill / "erp_reader_client.py").read_bytes() == (
        skill.parent / "sc_log_reader/src/sc_log_reader/feed.py"
    ).read_bytes()


def test_dashboard_card_matches_navpoint_and_cancels_on_unload(adapter, tmp_path, monkeypatch):
    cards = []
    pauses = []
    async def emit(message, **kwargs):
        cards.append((message, kwargs))
    async def immediate(seconds): pauses.append(seconds)
    async def run():
        skill = adapter.SC_Accountant({"data_dir": str(tmp_path), "auto_sync_interval": 0},
                                     wingman=types.SimpleNamespace(name="Computer"))
        skill.printr = types.SimpleNamespace(print_async=emit)
        await skill.prepare()
        try:
            assert skill._server is not None
            assert skill._announce_task is not None
            skill._announce_task.cancel()
            await asyncio.gather(skill._announce_task, return_exceptions=True)
            skill._poll_task.cancel()
            await asyncio.gather(skill._poll_task, return_exceptions=True)
            with monkeypatch.context() as patch:
                patch.setattr(adapter.asyncio, "sleep", immediate)
                await skill._announce_ui_startup(skill._server)
            assert len(cards) == 1
            text, fields = cards[0]
            assert text == "Accountant dashboard ready.\nScan with your phone, or open:\nhttp://127.0.0.1:7863"
            assert fields["source_name"] == "Computer"
            from api.enums import LogType, LogSource
            assert fields["source"] == LogSource.WINGMAN
            assert fields["color"] == LogType.POSITIVE
            assert pauses == [15]
            assert fields["additional_data"]["image_base64"]
            assert "192.168" not in text
            old = skill._server
            await skill.unload()
            with monkeypatch.context() as patch:
                patch.setattr(adapter.asyncio, "sleep", immediate)
                await skill._announce_ui_startup(old)
            assert len(cards) == 1
            assert skill._announce_task is None
        finally:
            await skill.unload()
    asyncio.run(run())


def test_no_network_startup_card_offers_only_computer_link(adapter, tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    skill = adapter.SC_Accountant({"data_dir": str(tmp_path)})
    skill._server = types.SimpleNamespace(url="http://127.0.0.1:7863", lan_url="")
    skill.printr = types.SimpleNamespace(print_async=AsyncMock())
    monkeypatch.setattr(adapter.asyncio, "sleep", AsyncMock())
    asyncio.run(skill._announce_ui_startup(skill._server))
    args, kwargs = skill.printr.print_async.call_args
    assert args[0] == "Accountant dashboard ready.\nOpen on this computer:\nhttp://127.0.0.1:7863"
    assert kwargs["additional_data"] is None


def test_dashboard_failure_does_not_stop_capture(adapter, tmp_path, monkeypatch):
    from skills.sc_accountant import erp_web
    def fail(_): raise OSError("Port already occupied")
    monkeypatch.setattr(erp_web.ERPServer, "start", fail)
    async def run():
        skill = adapter.SC_Accountant({"data_dir": str(tmp_path), "auto_sync_interval": 0})
        await skill.prepare()
        try:
            assert skill._engine is not None
            assert skill._poll_task is not None
            assert skill._server is None
            assert skill._announce_task is None
        finally:
            await skill.unload()
    asyncio.run(run())


def test_qr_image_uses_exact_navpoint_format():
    from skills.sc_accountant.erp_sharing import qr_png_base64
    import importlib.util
    root = Path(__file__).resolve().parents[2] / "sc_navpoint/navpoint_ui"
    spec = importlib.util.spec_from_file_location("_nav_qr_check", root / "__init__.py",
                                                 submodule_search_locations=[str(root)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = package
    try:
        spec.loader.exec_module(package)
        sharing = importlib.import_module(spec.name + ".sharing")
        url = "http://192.168.1.20:7863/?share=abcdefghijklmnop"
        assert qr_png_base64(url) == sharing.qr_png_base64(url)
    finally:
        for name in list(sys.modules):
            if name == spec.name or name.startswith(spec.name + "."):
                sys.modules.pop(name)


def reader_profile(directory, module="skills.sc_log_reader.main"):
    return types.SimpleNamespace(config=types.SimpleNamespace(skills=[
        types.SimpleNamespace(module=module, custom_properties=[
            types.SimpleNamespace(id="runtime_directory", value=str(directory))
        ])
    ]))


@pytest.mark.parametrize("module", ["skills.sc_log_reader.main", "skills.sc_log_reader_2.main"])
def test_blank_reader_path_discovers_profile_runtime_without_creating_it(adapter, tmp_path, module):
    runtime = tmp_path / "custom reader folder"
    skill = adapter.SC_Accountant({"data_dir": str(tmp_path / "accountant")},
                                 wingman=reader_profile(runtime, module))
    assert skill._reader_path() == runtime / "events.sqlite3"
    assert not runtime.exists()


def test_manual_reader_path_takes_priority_and_settings_remain_live(adapter, tmp_path):
    host = reader_profile(tmp_path / "reader")
    config = {"reader_database": str(tmp_path / "explicit.sqlite3")}
    skill = adapter.SC_Accountant(config, wingman=host)
    assert skill._reader_path() == tmp_path / "explicit.sqlite3"
    config["reader_database"] = ""
    assert skill._reader_path() == tmp_path / "reader/events.sqlite3"
    host.config.skills[0].custom_properties[0].value = str(tmp_path / "moved")
    assert skill._reader_path() == tmp_path / "moved/events.sqlite3"


def test_discovery_refuses_ambiguous_readers_and_ignores_unrelated_skills(adapter, tmp_path):
    host = reader_profile(tmp_path / "first")
    host.config.skills += reader_profile(tmp_path / "second").config.skills
    skill = adapter.SC_Accountant({}, wingman=host)
    with pytest.raises(ValueError, match="Multiple"):
        skill._reader_path()
    host.config.skills = reader_profile(tmp_path / "unrelated", "skills.other.main").config.skills
    assert skill._reader_path() is None


def test_discovery_uses_actual_v3_readonly_config_facade(adapter, tmp_path):
    from api.interface import SkillConfig
    from pydantic import BaseModel
    from wingmen.wingman_context import WingmanContext

    class Profile(BaseModel):
        skills: list[SkillConfig]

    profile = Profile(skills=[SkillConfig(
        module="skills.sc_log_reader.main", name="SCLogReader",
        display_name="Star Citizen Log Reader", description={"en": "Reader"},
        custom_properties=[{"id": "runtime_directory", "name": "Runtime",
                            "value": str(tmp_path), "property_type": "string"}],
    )])
    host = WingmanContext(types.SimpleNamespace(config=profile))
    before = profile.model_dump()
    skill = adapter.SC_Accountant({}, wingman=host)
    assert skill._reader_path() == tmp_path / "events.sqlite3"
    assert profile.model_dump() == before


def test_auto_capture_waits_for_reader_then_resumes_once_after_restart(adapter, tmp_path, monkeypatch):
    skills = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(skills / "sc_log_reader/src"))
    from sc_log_reader.service import Service
    from sc_log_reader.reader import Record

    runtime = tmp_path / "reader"
    config = {"data_dir": str(tmp_path / "accountant"), "auto_sync_interval": 0.1}
    host = reader_profile(runtime)

    async def until(predicate):
        for _ in range(100):
            if predicate():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("Capture did not reach expected state")

    async def run():
        skill = adapter.SC_Accountant(config, wingman=host)
        reader = None
        await skill.prepare()
        try:
            await until(lambda: "waiting" in skill._feed_status.lower())
            assert not runtime.exists()
            reader = Service(runtime)
            line = '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.'
            reader.ingest(Record(line, 0, len(line)), "LIVE", "fresh-install")
            await until(lambda: "active" in skill._feed_status.lower())
            assert skill._engine.view()["data"]["balance"] == "500.00"
            await skill.unload()
            skill = adapter.SC_Accountant(config, wingman=host)
            await skill.prepare()
            await until(lambda: "active" in skill._feed_status.lower())
            assert skill._engine.view()["data"]["balance"] == "500.00"
            original_cursor = skill._engine.view("feed")["data"]["cursor"]
            replacement = Service(tmp_path / "replacement")
            try:
                host.config.skills[0].custom_properties[0].value = str(replacement.root)
                await until(lambda: "database changed" in skill._feed_status.lower())
                assert skill._engine.view()["data"]["balance"] == "500.00"
                assert skill._engine.view("feed")["data"]["cursor"] == original_cursor
                host.config.skills[0].custom_properties[0].value = str(runtime)
                await until(lambda: "active" in skill._feed_status.lower())
            finally:
                replacement.close()
        finally:
            await skill.unload()
            if reader:
                reader.close()

    asyncio.run(run())
