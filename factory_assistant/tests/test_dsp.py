"""Dyson Sphere Program short reader, catalog, report and GameHandler."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dsp_save_builder import build_save, factory_stat, product_stat  # noqa: E402

from factory_games.dyson_sphere_program.game import DysonSphereProgramHandler  # noqa: E402
from factory_games.dyson_sphere_program.handler import report  # noqa: E402
from factory_games.dyson_sphere_program.reader import saves  # noqa: E402
from factory_games.dyson_sphere_program.reader.catalog import load_catalog  # noqa: E402
from factory_games.dyson_sphere_program.reader.save_file import DspSaveError, read_save  # noqa: E402
from factory_shared.contract import HandlerContext  # noqa: E402

IRON_ORE, IRON_INGOT, MAGNET = 1001, 1101, 1102
MW = 60 * 1_000_000  # one MW for one minute in the 1-minute pool (W * 60 s)


def _home_factory() -> bytes:
    return factory_stat(
        [
            product_stat(IRON_ORE, [10, 60, 600, 3600], [15, 90, 900, 5400]),
            product_stat(IRON_INGOT, [15, 90, 900, 5400], [5, 30, 300, 1800]),
        ],
        # generated, consumed, charged, discharged, research hash
        [[MW, 5 * MW, 50 * MW, 300 * MW], [MW, 4 * MW, 40 * MW, 240 * MW], [0], [0], [600, 3600, 36000, 216000]],
    )


def _empty_factory() -> bytes:
    return factory_stat([], [[0, 2 * MW, 20 * MW], [0, 3 * MW, 30 * MW]])


# --- reader ---


def test_reads_header_galaxy_and_statistics(tmp_path: Path) -> None:
    path = build_save(tmp_path / "a.dsv", factories=[_empty_factory(), _home_factory()])
    summary = read_save(path)

    assert summary.version_text == "0.10.35.29104"
    assert summary.galaxy_seed == 12345 and summary.star_count == 64
    assert summary.identity == "dsp-12345-64"
    assert summary.game_name == "My Galaxy"
    assert summary.stats_found and len(summary.factories) == 2
    home = summary.factories[1]
    assert home.items[IRON_ORE].produced[:4] == (10, 60, 600, 3600)
    assert home.items[IRON_ORE].consumed[2] == 900
    assert home.power["generated"][1] == 5 * MW
    assert summary.factories[0].items == {}


def test_new_game_without_buildings_has_no_statistics(tmp_path: Path) -> None:
    summary = read_save(build_save(tmp_path / "new.dsv", factories=[]))
    assert not summary.stats_found
    assert summary.notes


def test_incomplete_save_is_refused(tmp_path: Path) -> None:
    path = build_save(tmp_path / "half.dsv", factories=[_home_factory()], truncate=True)
    with pytest.raises(DspSaveError, match="incomplete"):
        read_save(path)


def test_not_a_save_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.dsv"
    path.write_bytes(b"NOTASAVE" + b"\x00" * 100)
    with pytest.raises(DspSaveError):
        read_save(path)


# --- save discovery ---


def test_newest_save_is_active_and_errored_autosave_is_ignored(tmp_path: Path) -> None:
    old = build_save(tmp_path / "Old.dsv")
    new = build_save(tmp_path / "_autosave_0.dsv")
    errored = build_save(tmp_path / "_autosave_errored.dsv")
    now = time.time()
    os.utime(old, (now - 300, now - 300))
    os.utime(new, (now - 100, now - 100))
    os.utime(errored, (now - 10, now - 10))

    found = saves.find_active_save(str(tmp_path), now=now)

    assert found.confirmed and found.path == new and not found.settling


def test_save_written_just_now_is_settling(tmp_path: Path) -> None:
    path = build_save(tmp_path / "_lastexit_.dsv")
    found = saves.find_active_save(str(tmp_path), now=path.stat().st_mtime + 0.5)
    assert found.settling


def test_missing_folder_and_empty_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(saves, "candidate_save_dirs", lambda configured="": [tmp_path / "nope"])
    assert saves.find_active_save().status == saves.STATUS_NO_SAVE_FOLDER
    monkeypatch.setattr(saves, "candidate_save_dirs", lambda configured="": [tmp_path])
    assert saves.find_active_save().status == saves.STATUS_NO_SAVE


# --- catalog ---


def test_bundled_catalog_has_english_names_and_recipes() -> None:
    catalog = load_catalog()
    assert catalog.item_name(IRON_ORE) == "Iron Ore"
    assert catalog.item_name(999_999) == "item 999999"
    ingot = catalog.recipes_making(IRON_INGOT)
    assert ingot and ingot[0].type == "smelt" and ingot[0].inputs == ((IRON_ORE, 1),)


# --- report ---


def test_rates_deficits_and_power(tmp_path: Path) -> None:
    summary = read_save(build_save(tmp_path / "a.dsv", factories=[_empty_factory(), _home_factory()]))
    catalog = load_catalog()

    rates = {r.item_id: r for r in report.cluster_rates(summary, catalog, 10)}
    assert rates[IRON_ORE].produced == pytest.approx(60.0)
    assert rates[IRON_ORE].consumed == pytest.approx(90.0)
    assert [r.item_id for r in report.deficits(list(rates.values()), 5)] == [IRON_ORE]
    assert [r.item_id for r in report.surpluses(list(rates.values()), 5)] == [IRON_INGOT]

    power = report.power_mw(summary, 10)
    assert power["generated"] == pytest.approx(7.0)  # 5 MW + 2 MW
    assert power["consumed"] == pytest.approx(7.0)
    assert power["research_hash"] == pytest.approx(60.0)
    lines = report.planet_lines(summary, 10, 5)
    assert any("Planet 1" in line and "use 3.0 MW of 2.0 MW capacity" in line and "at power limit" in line for line in lines)
    assert any("Warning" in line for line in report.power_lines(summary, 10))


def test_short_play_time_does_not_dilute_rates(tmp_path: Path) -> None:
    # 5 minutes played: the 10-minute total covers only 5 minutes.
    summary = read_save(build_save(tmp_path / "a.dsv", game_tick=5 * 3600, factories=[_home_factory()]))
    rates = {r.item_id: r for r in report.cluster_rates(summary, load_catalog(), 10)}
    assert rates[IRON_ORE].produced == pytest.approx(120.0)


def test_lookup_finds_item_and_recipe() -> None:
    lines = report.lookup_lines(load_catalog(), "iron ingot")
    assert any("Item Iron Ingot" in line for line in lines)
    assert any("Recipe Iron Ingot" in line and "Iron Ore" in line for line in lines)


# --- GameHandler ---


def _handler(tmp_path: Path, save_dir: Path, writes: bool = True) -> DysonSphereProgramHandler:
    settings = {"dsp_save_dir": str(save_dir), "dsp_rate_window_minutes": 10}
    return DysonSphereProgramHandler(
        HandlerContext(
            generated_dir=lambda: tmp_path / "generated",
            setting=settings.get,
            diag=lambda message: None,
            show_map=lambda path: "shown",
            max_response_items=lambda: 12,
            allow_plan_writes=lambda: writes,
        )
    )


def _aged_save(save_dir: Path, **kwargs) -> Path:
    save_dir.mkdir(parents=True, exist_ok=True)
    path = build_save(save_dir / "_autosave_0.dsv", **kwargs)
    past = time.time() - 60
    os.utime(path, (past, past))
    return path


def test_handler_context_audit_and_journal(tmp_path: Path) -> None:
    save_dir = tmp_path / "Save"
    _aged_save(save_dir, factories=[_empty_factory(), _home_factory()])
    handler = _handler(tmp_path, save_dir)

    assert handler.active_save().confirmed
    context = asyncio.run(handler.context(lookup="iron ingot"))
    assert "galaxy seed 12345" in context
    assert "Iron Ore: make 60, use 90" in context
    assert "Recipe Iron Ingot" in context

    audit = asyncio.run(handler.calculate(mode="audit"))
    assert "capacity 7.0 MW, use 7.0 MW (100% of capacity)" in audit and "Warning" in audit and "Most extra" in audit
    assert "not available" in asyncio.run(handler.calculate(mode="plan"))
    assert "not available" in asyncio.run(handler.show_map("oil"))

    saved = asyncio.run(handler.update_journal("add_note", title="Build more iron smelters"))
    assert saved.startswith("Saved the note")
    assert "Build more iron smelters" in asyncio.run(handler.context())


def test_handler_messages_without_saves(tmp_path: Path) -> None:
    handler = _handler(tmp_path, tmp_path / "missing")
    handler_dir = tmp_path / "missing"
    assert not handler_dir.exists()
    reply = asyncio.run(handler.context())
    assert "save folder" in reply or "no saves" in reply


def test_auto_refresh_reads_each_new_save_once(tmp_path: Path) -> None:
    save_dir = tmp_path / "Save"
    _aged_save(save_dir, factories=[_home_factory()])
    messages: list[str] = []
    handler = _handler(tmp_path, save_dir)
    handler._ctx.diag = messages.append

    asyncio.run(handler.auto_refresh_once())
    asyncio.run(handler.auto_refresh_once())

    assert len(messages) == 1 and "1 planets" in messages[0]


@pytest.mark.skipif(not os.environ.get("DSP_SAMPLE_SAVE"), reason="set DSP_SAMPLE_SAVE to a real .dsv")
def test_real_save_from_environment() -> None:
    summary = read_save(Path(os.environ["DSP_SAMPLE_SAVE"]))
    assert summary.stats_found and summary.factories


def test_planet_powered_by_accumulators_is_not_short(tmp_path: Path) -> None:
    # generated 0, consumed 3 MW, discharged 4 MW (exchangers / accumulators)
    remote = factory_stat([], [[0], [0, 3 * MW, 30 * MW], [0], [0, 4 * MW, 40 * MW]])
    summary = read_save(build_save(tmp_path / "a.dsv", factories=[remote, _home_factory()]))
    lines = report.planet_lines(summary, 10, 5)
    assert any("Planet 1" in line and "of 4.0 MW capacity" in line and "limit" not in line for line in lines)


def test_new_game_with_only_hand_work_shows_all_time_totals(tmp_path: Path) -> None:
    # Like a real 0.10.35 start: only the all-time total (index 6) has values.
    early = factory_stat([product_stat(1030, [0, 0, 0, 0, 0, 0, 769], [0, 0, 0, 0, 0, 0, 198])], [[0]])
    summary = read_save(build_save(tmp_path / "_autosave_0.dsv", game_tick=15 * 3600, factories=[early]))
    lines = report.production_lines(summary, load_catalog(), 10, 12)
    assert "No machines produced anything" in lines[0]
    assert "Log 769" in lines[1]
    header = report.header_lines(summary)[0]
    assert header.startswith("Active save: My Galaxy (from autosave)")


def test_ten_minute_rate_matches_the_statistics_panel(tmp_path: Path) -> None:
    # Real values from the "Absolutist" save (0.10.35): the in-game panel showed
    # Coal 240.0/min and Iron Ingot use 225.0/min for "10 minutes".
    coal = product_stat(1006, [40, 240, 2400, 12159], [40, 242, 2402, 15652])
    ingot = product_stat(IRON_INGOT, [38, 226, 2616, 10386], [38, 225, 2250, 8104])
    summary = read_save(build_save(tmp_path / "a.dsv", game_tick=117 * 3600, factories=[factory_stat([coal, ingot], [[0]])]))
    rates = {r.item_id: r for r in report.cluster_rates(summary, load_catalog(), 10)}
    assert rates[1006].produced == pytest.approx(240.0)
    assert rates[IRON_INGOT].consumed == pytest.approx(225.0)


def test_power_matches_the_power_tab(tmp_path: Path) -> None:
    # Real totals from "Absolutist" 00:50:25; Power tab showed capacity 30.9 MW,
    # total energy consumption 150 GJ, 100 % sufficiency.
    gen = [309_600_000, 1_858_721_126, 18_684_456_744]
    use = [188_801_287, 1_135_497_339, 7_961_315_100]
    factory = factory_stat([product_stat(1006, [1, 1, 1], [1, 1, 1])], [gen, use])
    summary = read_save(build_save(tmp_path / "a.dsv", game_tick=229 * 3600, factories=[factory]))
    line = report.power_lines(summary, 10)[0]
    assert "capacity 31.0 MW, use 18.9 MW (61% of capacity)" in line
    assert "10-min average use 13.3 MW" in line
    assert not any("Warning" in text for text in report.power_lines(summary, 10))
