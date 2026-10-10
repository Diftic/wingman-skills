"""Check the repository's loadable skill against its maintained source files.

The Git folder also carries the tested portable runtime. Check both copies before
publishing a change; build_target_candidate.py produces the distributable ZIP.
"""
from pathlib import Path


def verify():
    root = Path(__file__).resolve().parents[1]
    for name in ("main.py", "default_config.yaml", "CONTRACT.md"):
        assert (root / name).read_bytes() == (root / "integrations/wingman_target" / name).read_bytes(), name
    source = root / "src/sc_log_reader"
    portable = root / "dependencies/sc_log_reader"
    expected = {p.relative_to(source) for p in source.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    actual = {p.relative_to(portable) for p in portable.rglob("*")
              if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    assert actual == expected, "Portable reader file list differs from source"
    for name in expected:
        assert (source / name).read_bytes() == (portable / name).read_bytes(), name
    return len(expected)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.info("Repository reader runtime matches %d source files", verify())
