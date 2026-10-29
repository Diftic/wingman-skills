"""Board members on disk: joining, staying, leaving, finding a member by name."""

from __future__ import annotations

import os

import pytest

from wai_board import Board, Member, slug


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


def member(name: str, role: str = "", answers: bool = True) -> Member:
    return Member(name=name, role=role, functions=["UEX Corp"], answers=answers)


def test_slug_is_readable_and_file_safe():
    assert slug("Professor Martin").startswith("professor_martin_")
    assert slug("  A/B:C  ").startswith("a_b_c_")
    assert "/" not in slug("A/B") and ":" not in slug("A:B")


def test_slug_ignores_case_and_outer_spaces_only():
    assert slug("ORIN") == slug("orin") == slug("  Orin ")


def test_slug_keeps_names_apart_that_differ_only_in_punctuation():
    assert slug("ORIN") != slug("ORIN!")


def test_slug_keeps_non_latin_letters_and_is_never_empty():
    assert slug("Ærlig").startswith("ærlig_")
    assert slug("!!!")
    assert slug("!!!") != slug("???")


def test_joined_members_are_listed_with_role_and_functions(board):
    board.join(member("ORIN", "Ship AI"))
    board.join(member("Professor Martin", "Research partner"))

    names = {m.name: m for m in board.members()}

    assert set(names) == {"ORIN", "Professor Martin"}
    assert names["Professor Martin"].role == "Research partner"
    assert names["Professor Martin"].functions == ["UEX Corp"]


def test_member_not_seen_for_two_minutes_is_gone(board, clock):
    board.join(member("ORIN"))
    clock.now += 121

    assert board.members() == []


def test_heartbeat_keeps_a_member(board, clock):
    board.join(member("ORIN"))
    clock.now += 100
    board.heartbeat("ORIN")
    clock.now += 100

    assert [m.name for m in board.members()] == ["ORIN"]


def test_leave_removes_the_member(board):
    board.join(member("ORIN"))
    board.leave("ORIN")

    assert board.members() == []


def test_resolve_matches_loosely_and_uniquely(board):
    board.join(member("ORIN"))
    board.join(member("Professor Martin"))

    assert board.resolve("professor martin").name == "Professor Martin"
    assert board.resolve("Professor").name == "Professor Martin"
    assert board.resolve("martin").name == "Professor Martin"
    assert board.resolve("nobody") is None


def test_resolve_refuses_an_ambiguous_name(board):
    board.join(member("Professor Martin"))
    board.join(member("Professor Oak"))

    assert board.resolve("professor") is None
    assert board.resolve("professor oak").name == "Professor Oak"


def test_member_files_are_complete_json_and_no_temp_files_remain(board, tmp_path):
    board.join(member("ORIN"))

    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert files and not any(p.name.endswith(".tmp") for p in files)


def test_board_creates_its_folders(tmp_path, clock):
    root = tmp_path / "nested" / "board"
    Board(root, clock=clock).join(member("ORIN"))

    assert os.path.isdir(root / "members")
