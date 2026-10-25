"""The board on disk: members, posting, claiming, forwarding rules, cleanup."""

from __future__ import annotations

import json
import os

import pytest

from wai_board import Board, BoardError, Member, Message, short_label, slug


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


def test_posted_task_lands_in_the_recipients_inbox(board):
    board.join(member("ORIN"))
    board.join(member("Professor Martin"))
    task = Message.task(sender="ORIN", to="Professor Martin", topic="Connie refit",
                        text="Cost of S4 repeaters?", answer_to="sender", now=board.now())

    board.post(task)
    inbox = board.inbox("Professor Martin")

    assert [m.id for m in inbox] == [task.id]
    assert inbox[0].topic == "Connie refit"
    assert inbox[0].path == ["ORIN"]
    assert board.inbox("ORIN") == []


def test_post_to_all_reaches_every_other_member_once(board):
    for name in ("ORIN", "Professor Martin", "Quartermaster"):
        board.join(member(name))
    task = Message.task(sender="ORIN", to="all", topic="Status", text="Docking now.",
                        answer_to="sender", now=board.now())

    written = board.post(task)

    assert sorted(m.to for m in written) == ["Professor Martin", "Quartermaster"]
    assert len(board.inbox("Professor Martin")) == 1
    assert len(board.inbox("Quartermaster")) == 1
    assert board.inbox("ORIN") == []


def test_post_to_all_skips_members_that_only_send(board):
    board.join(member("ORIN"))
    board.join(member("Logger", answers=False))
    task = Message.task(sender="ORIN", to="all", topic="t", text="x", answer_to="sender",
                        now=board.now())

    assert board.post(task) == []


def test_files_are_complete_json_and_no_temp_files_remain(board, tmp_path):
    board.join(member("Professor Martin"))
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())
    board.post(task)

    files = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert not any(p.name.endswith(".tmp") for p in files)
    for p in files:
        json.loads(p.read_text(encoding="utf-8"))


def test_a_message_can_be_claimed_only_once(board):
    board.join(member("Professor Martin"))
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())
    board.post(task)

    assert board.claim("Professor Martin", task.id) is True
    assert board.claim("Professor Martin", task.id) is False
    assert board.inbox("Professor Martin") == []


def test_reply_goes_back_to_the_original_sender(board):
    task = Message.task(sender="ORIN", to="Professor Martin", topic="Connie refit",
                        text="Cost?", answer_to="sender", now=board.now())

    reply = task.reply(sender="Professor Martin", text="340k aUEC.", delivered_to_user=False,
                       now=board.now())

    assert reply.kind == "reply"
    assert reply.to == "ORIN"
    assert reply.in_reply_to == task.id
    assert reply.thread == task.thread
    assert reply.topic == "Connie refit"


def test_forward_keeps_the_thread_and_the_original_sender(board):
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())

    forwarded = task.forward(by="Professor Martin", to="Quartermaster", note="Prices are yours.",
                             max_hops=3, now=board.now())

    assert forwarded.to == "Quartermaster"
    assert forwarded.thread == task.thread
    assert forwarded.reply_to == "ORIN"
    assert forwarded.hops == 1
    assert forwarded.path == ["ORIN", "Professor Martin"]
    assert "Prices are yours." in forwarded.text


def test_forward_refuses_past_the_hop_limit(board):
    task = Message.task(sender="A", to="B", topic="t", text="x", answer_to="sender",
                        now=board.now())
    hop1 = task.forward(by="B", to="C", note="", max_hops=2, now=board.now())
    hop2 = hop1.forward(by="C", to="D", note="", max_hops=2, now=board.now())

    with pytest.raises(BoardError):
        hop2.forward(by="D", to="E", note="", max_hops=2, now=board.now())


def test_forward_refuses_to_send_a_task_back_into_its_chain(board):
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())

    with pytest.raises(BoardError):
        task.forward(by="Professor Martin", to="ORIN", note="", max_hops=3, now=board.now())


def test_a_reply_cannot_be_forwarded(board):
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())
    reply = task.reply(sender="Professor Martin", text="done", delivered_to_user=False,
                       now=board.now())

    with pytest.raises(BoardError):
        reply.forward(by="ORIN", to="Quartermaster", note="", max_hops=3, now=board.now())


def test_a_task_needs_no_topic_and_gets_a_short_label_from_the_message(board):
    task = Message.task(sender="ORIN", to="Professor Martin",
                        text="What does it cost to refit my Constellation MK V with size 4 "
                             "ballistic repeaters, and where do I buy them?",
                        answer_to="sender", now=board.now())

    assert task.topic == "What does it cost to refit my Constellation MK V…"
    assert task.sender == "ORIN"


def test_short_label_keeps_short_messages_whole():
    assert short_label("  Where to buy LUX?  ") == "Where to buy LUX?"
    assert short_label("one\ntwo   three") == "one two three"
    assert short_label("") == "a task"


def test_task_rejects_an_unknown_answer_to():
    with pytest.raises(BoardError):
        Message.task(sender="A", to="B", topic="t", text="x", answer_to="somewhere", now=0.0)


def test_cleanup_deletes_handled_messages_older_than_a_day(board, clock):
    board.join(member("Professor Martin"))
    old = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="old",
                       answer_to="sender", now=board.now())
    board.post(old)
    board.claim("Professor Martin", old.id)
    board.finish("Professor Martin", old.id)
    clock.now += 2 * 86400
    board.heartbeat("Professor Martin")
    new = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="new",
                       answer_to="sender", now=board.now())
    board.post(new)

    removed = board.cleanup()

    assert removed == 1
    assert [m.id for m in board.inbox("Professor Martin")] == [new.id]


def test_cleanup_leaves_files_it_cannot_read(board, clock, tmp_path):
    folder = tmp_path / "messages" / slug("Professor Martin")
    folder.mkdir(parents=True)
    (folder / "locked.taken").write_text("{half a file", encoding="utf-8")
    clock.now += 10 * 86400

    assert board.cleanup() == 0
    assert (folder / "locked.taken").exists()


def test_abandoned_taken_tasks_go_back_to_the_inbox(board, tmp_path):
    board.join(member("Professor Martin"))
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())
    board.post(task)
    board.claim("Professor Martin", task.id)
    taken = tmp_path / "messages" / slug("Professor Martin") / f"{task.id}.taken"
    old = taken.stat().st_mtime - 3600
    os.utime(taken, (old, old))

    assert board.requeue_abandoned("Professor Martin") == 1
    assert [m.id for m in board.inbox("Professor Martin")] == [task.id]


def test_a_task_being_worked_on_now_is_not_requeued(board):
    board.join(member("Professor Martin"))
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="sender", now=board.now())
    board.post(task)
    board.claim("Professor Martin", task.id)

    assert board.requeue_abandoned("Professor Martin") == 0
    assert board.inbox("Professor Martin") == []


def test_a_broken_message_file_is_skipped_not_fatal(board, tmp_path):
    board.join(member("Professor Martin"))
    inbox_dir = tmp_path / "messages" / slug("Professor Martin")
    inbox_dir.mkdir(parents=True, exist_ok=True)
    (inbox_dir / "broken.json").write_text("{not json", encoding="utf-8")

    assert board.inbox("Professor Martin") == []


def test_message_round_trips_through_json(board):
    task = Message.task(sender="ORIN", to="Professor Martin", topic="t", text="x",
                        answer_to="user", now=board.now())

    again = Message.from_dict(json.loads(json.dumps(task.to_dict())))

    assert again == task


def test_board_creates_its_folders(tmp_path, clock):
    root = tmp_path / "nested" / "board"
    Board(root, clock=clock).join(member("ORIN"))

    assert os.path.isdir(root / "members")
