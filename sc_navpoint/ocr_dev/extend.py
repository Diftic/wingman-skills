"""Fold newly identified glyphs into the template set and save it.

DEV TOOL, not a runtime file.

The login-screen capture only showed the characters that screen displayed, so
it yielded 65 templates over 41 characters: 17 characters had only ONE of their
two sub-pixel phases, and `3`, `k`, `g`, `w` were absent entirely.

Labels here come from LOOKING AT ONE MAGNIFIED GLYPH at a time
(`captures/game-mid/unknown_core.png`), not from transcribing a line by eye.
That distinction matters: eye-transcription of a line has produced a wrong
answer twice in this project, both times by miscounting a run of spaces, while
identifying a single rendered glyph has no such failure mode.

The template set is a BANK that grows capture by capture, so this starts from
the existing `glyphs.npz` when one exists rather than from the login templates:
starting from the base would silently discard everything harvested since, which
is a data loss that looks like a normal successful run. An existing template is
never replaced without `--allow-replace`, because replacing one already
regressed every `5` at one phase into an `S`, and the tell was the replace count.

Usage:

    python extend.py --label game-mid --out glyphs.npz
    python extend.py --label <new> --labels <new>_labels.json

Credit: Mallachi
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from decode import build_templates


CAPTURE_ROOT = Path(__file__).parent / "captures"
BANK = Path(__file__).parent / "glyphs.npz"

# index in unknown.json -> character. Entries 12, 14 and 15 are deliberately
# absent: they render as fragments rather than whole glyphs and carry only two
# instances each, so naming them would be a guess. They stay unknown, which
# costs a little accuracy and risks nothing.
LABELS: dict[int, str] = {
    0: "3", 1: "3", 2: "k", 3: "g", 4: "d", 5: "9", 6: "_", 7: "p",
    8: "w", 9: "n", 10: "b", 11: "u",
}
# Index 13 was labelled "5" and REGRESSED the decode: every real 5 at that
# phase then read as S. extend.py reported it as replacing an existing
# template, which was the tell. It is an S, not a 5, and the existing template
# it overwrote was correct. Left unlabelled rather than re-guessed.


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--label", required=True)
    parser.add_argument("--templates", default="login")
    parser.add_argument("--base", default=None,
                        help="npz bank to grow, or 'login' for the base set")
    parser.add_argument("--labels", default=None,
                        help="JSON file of {index: character} for this capture")
    parser.add_argument("--allow-replace", action="store_true",
                        help="permit overwriting an existing template")
    parser.add_argument("--out", default="glyphs.npz")
    args = parser.parse_args(argv)

    base = args.base or (str(BANK) if BANK.exists() else args.templates)
    if base == "login" or base == args.templates and not Path(base).exists():
        glyphs = build_templates(args.templates)
    else:
        data = np.load(base)
        glyphs = {
            (k.split("|")[0], int(k.split("|")[1])): data[k] for k in data.files
        }
    print(f"base: {base}, {len(glyphs)} templates over "
          f"{len({c for c, _ in glyphs})} characters")

    if args.labels:
        labels = {int(k): v for k, v in json.load(open(args.labels)).items()}
    else:
        labels = LABELS

    found = json.load(open(CAPTURE_ROOT / args.label / "unknown.json"))
    added = replaced = refused = 0
    for entry in found:
        index = entry["index"]
        if index not in labels:
            continue
        char = labels[index]
        phase = entry["phase"]
        key = (char, phase)
        if key in glyphs:
            # A replace is a RED FLAG, not a routine outcome: the existing
            # template was measured from a real instance, so a collision means
            # either this label is wrong or that one was.
            if not args.allow_replace:
                print(f"  REFUSED to replace existing template {char!r}/{phase} "
                      f"(index {index}); pass --allow-replace if that is intended")
                refused += 1
                continue
            replaced += 1
        else:
            added += 1
        glyphs[key] = np.clip(np.asarray(entry["map"], dtype=np.float64), 0.0, 1.0)

    print(f"added {added} new (character, phase) templates, replaced {replaced}, "
          f"refused {refused}")
    print(f"now:  {len(glyphs)} templates over "
          f"{len({c for c, _ in glyphs})} characters")
    missing = sorted(
        c for c in {c for c, _ in glyphs}
        if not ((c, 0) in glyphs and (c, 1) in glyphs)
    )
    print(f"characters still lacking one phase ({len(missing)}): {''.join(missing)}")

    out = Path(__file__).parent / args.out
    np.savez(out, **{f"{c}|{p}": g for (c, p), g in glyphs.items()})
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
