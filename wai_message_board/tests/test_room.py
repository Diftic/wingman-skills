"""Room rules: who a line addresses, when a Wingman answers, and the brake on banter."""

from __future__ import annotations

from wai_board import (USER, ChatLine, banter_streak, mentioned, should_answer,
                       wingman_lines_since_user)

MEMBERS = ["ORIN", "Professor Martin", "Quartermaster"]


def line(n: int, speaker: str, text: str, t: float = 100.0, member: str | None = None) -> ChatLine:
    return ChatLine(id=f"l{n}", member=member or speaker, speaker=speaker, text=text, time=t)


def answers(me: str, said: ChatLine, room: list[ChatLine], *, max_streak: int = 6,
            now: float = 101.0, members: list[str] = MEMBERS) -> bool:
    return should_answer(me, said, room, member_names=members, max_streak=max_streak,
                         max_age=60, now=now)


def test_full_name_and_single_name_words_are_mentions():
    assert mentioned("Professor Martin, where is LUX sold?", MEMBERS) == ["Professor Martin"]
    assert mentioned("Ask the professor.", MEMBERS) == ["Professor Martin"]
    assert mentioned("Martin knows.", MEMBERS) == ["Professor Martin"]
    assert mentioned("orin, spin her up", MEMBERS) == ["ORIN"]


def test_names_inside_other_words_are_not_mentions():
    assert mentioned("The origin of the professorship", MEMBERS) == []
    assert mentioned("ORINOCO", MEMBERS) == []


def test_several_members_can_be_mentioned():
    assert mentioned("ORIN and the Quartermaster disagree.", MEMBERS) == ["ORIN", "Quartermaster"]


def test_a_word_shared_by_two_names_calls_neither():
    names = ["Professor Martin", "Professor Oak"]

    assert mentioned("Professor, a word?", names) == []
    assert mentioned("Professor Oak, a word?", names) == ["Professor Oak"]
    assert mentioned("Martin, a word?", names) == ["Professor Martin"]


def test_common_words_inside_a_name_do_not_trigger():
    names = ["Star Citizen Helper", "The Doctor"]

    assert mentioned("Star Citizen patch 4.10 is out.", names) == []
    assert mentioned("Helper, check the patch.", names) == ["Star Citizen Helper"]
    assert mentioned("the doctor is in", names) == ["The Doctor"]  # the full name still counts


def test_streak_counts_wingman_lines_since_the_user_last_spoke():
    room = [line(1, USER, "hi", member="ORIN"), line(2, "ORIN", "a"),
            line(3, "Professor Martin", "b"), line(4, "ORIN", "c")]

    assert banter_streak(room, "l1") == 0
    assert banter_streak(room, "l2") == 1
    assert banter_streak(room, "l4") == 3
    assert banter_streak(room, "missing") == 0
    assert wingman_lines_since_user(room) == 3
    assert wingman_lines_since_user([*room, line(5, USER, "stop", member="ORIN")]) == 0


def test_a_wingman_answers_when_another_wingman_names_it():
    said = line(2, "ORIN", "Professor, where can the Captain buy LUX?", t=100.0)
    room = [line(1, USER, "ORIN, ask the professor about LUX", member="ORIN"), said]

    assert answers("Professor Martin", said, room, now=110.0)


def test_nobody_answers_a_user_line_core_already_routes_it():
    said = line(1, USER, "Professor Martin, what is Nyx?", member="Professor Martin")

    assert not answers("Professor Martin", said, [said])


def test_a_wingman_ignores_its_own_lines():
    said = line(1, "Professor Martin", "As Professor Martin, I say no.")

    assert not answers("Professor Martin", said, [said])


def test_lines_not_naming_the_wingman_are_left_alone():
    said = line(1, "ORIN", "Shields to front, Captain.")

    assert not answers("Professor Martin", said, [said])


def test_old_lines_are_not_answered():
    said = line(1, "ORIN", "Professor?", t=100.0)

    assert not answers("Professor Martin", said, [said], now=161.0)


def test_a_line_is_not_answered_once_the_user_has_spoken_after_it():
    said = line(2, "ORIN", "Professor, thoughts?", t=100.0)
    room = [said, line(3, USER, "never mind", t=105.0, member="ORIN")]

    assert not answers("Professor Martin", said, room, now=106.0)


def test_the_brake_stops_banter_until_the_user_speaks_again():
    room = [line(1, USER, "go", member="ORIN")]
    room += [line(n, "ORIN" if n % 2 else "Professor Martin",
                  "Professor, no." if n % 2 else "ORIN, yes.") for n in range(2, 8)]
    last = room[-1]  # line 7: ORIN talking to the Professor, the 6th Wingman line in a row

    assert not answers("Professor Martin", last, room, max_streak=6)
    assert answers("Professor Martin", last, room, max_streak=7)


def test_the_brake_counts_every_wingman_line_not_just_the_one_answered():
    # One early line named two Wingmen; four more Wingman lines followed. Answering the early
    # line now would be the 6th Wingman line in a row.
    early = line(2, "ORIN", "Professor and Quartermaster, opinions?")
    room = [line(1, USER, "go", member="ORIN"), early,
            *[line(n, "Professor Martin", "Hm.") for n in range(3, 7)]]

    assert banter_streak(room, early.id) == 1
    assert not answers("Quartermaster", early, room, max_streak=5)
