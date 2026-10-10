"""Local allowlist guard. Never copies, commits, pushes, or edits policy."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys


def git(repo, *args):
    result = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(repo), *args],
        capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", "replace").strip())
    return result.stdout.decode("utf-8", "surrogateescape")


def names(text):
    return [name for name in text.split("\0") if name]


def validate_path(name):
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or ".." in path.parts
            or "\\" in name or ":" in name or str(path) != name
            or any(part.lower() == ".git" for part in path.parts)):
        raise ValueError("Unsafe allowlist path: " + name)


def check(policy, commit=None):
    repo = Path(policy["checkout"]).resolve(strict=True)
    base = policy["base"]
    allowed = policy["files"]
    if not allowed:
        raise ValueError("Empty allowlist")
    for name in allowed:
        validate_path(name)
    actual_root = Path(git(repo, "rev-parse", "--show-toplevel").strip()).resolve()
    if actual_root != repo:
        raise ValueError("Checkout is not the configured repository root")
    branch = git(repo, "branch", "--show-current").strip()
    if branch != policy["branch"]:
        raise ValueError("Wrong contribution branch: " + branch)
    head = commit or "HEAD"
    git(repo, "merge-base", "--is-ancestor", base, head)
    commits = git(repo, "rev-list", "--reverse", f"{base}..{head}").splitlines()
    if git(repo, "rev-list", "--merges", f"{base}..{head}").strip():
        raise ValueError("Merge commits are not allowed in contribution history")

    def check_tree(tree, required):
        staged = tree is None
        diff_args = ["diff", "--name-only", "-z", "--no-renames"]
        diff_args += ["--cached", base] if staged else [base, tree]
        changed = names(git(repo, *diff_args, "--"))
        for name in changed:
            if name not in allowed:
                raise ValueError("Unapproved path: " + name)
        if staged:
            entries = {}
            for entry in names(git(repo, "ls-files", "--stage", "-z")):
                fields, name = entry.split("\t", 1)
                mode, blob, stage = fields.split()
                if stage != "0":
                    raise ValueError("Unresolved index conflict: " + name)
                entries[name] = (mode, blob)
        else:
            entries = {}
            for entry in names(git(repo, "ls-tree", "-r", "-z", tree)):
                fields, name = entry.split("\t", 1)
                mode, kind, blob = fields.split()
                entries[name] = (mode, blob)
        for name in (allowed if required else changed):
            if name not in entries:
                raise ValueError("Missing approved file: " + name)
            mode, blob = entries[name]
            if mode != "100644" or blob != allowed[name]["blob"]:
                raise ValueError("Unreviewed content: " + name)

    # Check every intermediate commit, not only the final diff.
    for revision in commits:
        check_tree(revision, required=False)
    if commit:
        check_tree(commit, required=True)
    else:
        check_tree(None, required=True)
        for name in names(git(repo, "diff", "--name-only", "-z", "--")):
            if name not in allowed:
                raise ValueError("Unapproved working change: " + name)
        # Include ignored untracked files: nothing local is silently swept in later.
        for name in names(git(repo, "ls-files", "--others", "-z")):
            if name not in allowed:
                raise ValueError("Unapproved local file: " + name)
        for name, entry in allowed.items():
            path = repo / name
            if not path.is_file():
                raise ValueError("Missing approved file: " + name)
            for parent in (path, *path.parents):
                if parent == repo:
                    break
                if parent.is_symlink() or parent.is_junction():
                    raise ValueError("Linked contribution file: " + name)
            if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError("Unreviewed content: " + name)
    return len(allowed), len(commits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--pre-push", nargs=2, metavar=("REMOTE", "URL"))
    args = parser.parse_args()
    try:
        policy = json.loads(args.policy.read_text(encoding="utf-8"))
        if args.pre_push:
            remote, url = args.pre_push
            if remote != "origin" or url != policy["fork_url"]:
                raise ValueError("Push destination must be the configured personal fork")
            updates = sys.stdin.read().splitlines()
            if not updates:
                raise ValueError("No push updates to inspect")
            expected_ref = "refs/heads/" + policy["branch"]
            for update in updates:
                local_ref, sha, remote_ref, old_sha = update.split()
                if local_ref != expected_ref or remote_ref != expected_ref or set(sha) == {"0"}:
                    raise ValueError("Only the configured topic branch may be pushed")
                check(policy, commit=sha)
        count, commits = check(policy)
        print(f"PASS: {count} approved files; {commits} contribution commits checked.")
        print("File scope and reviewed content verified; runtime qualification is separate.")
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("BLOCKED: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
