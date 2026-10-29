"""The shared chat log: each member appends its own lines, any member reads them."""

from __future__ import annotations

import pytest

from wai_board import CHAT_MAX_TEXT, Board, slug


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def board(tmp_path, clock) -> Board:
    return Board(tmp_path, clock=clock)


def test_lines_are_read_back_newest_last(board, clock):
    board.append_chat("ORIN", "User", "Where's the nearest refinery?")
    clock.now += 5
    board.append_chat("ORIN", "ORIN", "CRU-L1, Captain.")

    lines = board.read_chat("ORIN", last=10)

    assert [(l.speaker, l.text) for l in lines] == [("User", "Where's the nearest refinery?"),
                                                    ("ORIN", "CRU-L1, Captain.")]
    assert lines[0].member == "ORIN"
    assert lines[1].time == clock.now


def test_append_returns_the_line_with_a_unique_id(board):
    first = board.append_chat("ORIN", "ORIN", "one")
    second = board.append_chat("ORIN", "ORIN", "two")

    assert first.id and second.id and first.id != second.id
    assert [l.id for l in board.read_chat("ORIN", last=10)] == [first.id, second.id]


def test_blank_text_appends_nothing_and_returns_none(board):
    assert board.append_chat("ORIN", "User", "  ") is None


def test_lines_written_without_an_id_still_get_a_stable_one(board, tmp_path):
    folder = tmp_path / "chat"
    folder.mkdir()
    (folder / f"{slug('ORIN')}.jsonl").write_text(
        '{"member": "ORIN", "speaker": "User", "text": "old line", "time": 5.0}\n', encoding="utf-8")

    first = board.read_chat("ORIN", last=10)[0].id
    again = board.read_chat("ORIN", last=10)[0].id

    assert first and first == again


def test_only_the_last_lines_are_returned(board):
    for i in range(30):
        board.append_chat("ORIN", "User", f"line {i}")

    lines = board.read_chat("ORIN", last=3)

    assert [l.text for l in lines] == ["line 27", "line 28", "line 29"]


def test_a_member_without_a_log_has_no_lines(board):
    assert board.read_chat("Professor Martin", last=10) == []


def test_all_members_are_merged_in_time_order_without_the_reader(board, clock):
    board.append_chat("ORIN", "User", "a")
    clock.now += 1
    board.append_chat("Professor Martin", "User", "b")
    clock.now += 1
    board.append_chat("ORIN", "ORIN", "c")
    clock.now += 1
    board.append_chat("Quartermaster", "User", "d")

    lines = board.read_all_chat(exclude="Quartermaster", last=10)

    assert [(l.member, l.text) for l in lines] == [("ORIN", "a"), ("Professor Martin", "b"),
                                                   ("ORIN", "c")]


def test_all_members_keeps_only_the_newest_lines_overall(board, clock):
    for i in range(5):
        board.append_chat("ORIN", "User", f"o{i}")
        clock.now += 1
        board.append_chat("Professor Martin", "User", f"p{i}")
        clock.now += 1

    lines = board.read_all_chat(exclude=None, last=3)

    assert [l.text for l in lines] == ["p3", "o4", "p4"]


def test_long_text_is_cut_and_blank_text_is_skipped(board):
    board.append_chat("ORIN", "ORIN", "x" * (CHAT_MAX_TEXT + 500))
    board.append_chat("ORIN", "User", "   ")

    lines = board.read_chat("ORIN", last=10)

    assert len(lines) == 1
    assert len(lines[0].text) <= CHAT_MAX_TEXT + 1


def test_a_broken_line_is_skipped(board, tmp_path):
    board.append_chat("ORIN", "User", "good")
    with open(tmp_path / "chat" / f"{slug('ORIN')}.jsonl", "a", encoding="utf-8") as file:
        file.write("{broken\n")
    board.append_chat("ORIN", "User", "also good")

    assert [l.text for l in board.read_chat("ORIN", last=10)] == ["good", "also good"]


def test_trim_keeps_the_newest_lines(board):
    for i in range(20):
        board.append_chat("ORIN", "User", f"line {i}")

    board.trim_chat("ORIN", keep=5)

    assert [l.text for l in board.read_chat("ORIN", last=100)] == [f"line {i}" for i in range(15, 20)]


def test_clear_chat_removes_the_log(board):
    board.append_chat("ORIN", "User", "secret")

    board.clear_chat("ORIN")

    assert board.read_chat("ORIN", last=10) == []
