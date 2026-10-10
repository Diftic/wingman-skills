# Clean Wingman contributions

This folder keeps contribution preparation separate from your development repo.

## Published contribution branches

All three branches were created directly from ShipBit develop, independently.
They are pushed to the personal fork only; no issues or pull requests were opened.

| Skill | Checkout folder | Commit | Selected files | Branch |
| --- | --- | --- | --- | --- |
| Log Reader | `checkout` | `1dc1c43` | 28 | [contrib/sc-log-reader](https://github.com/Diftic/wingman-ai/tree/contrib/sc-log-reader) |
| NavPoint | `navpoint` | `fc8727c` | 53 | [contrib/sc-navpoint](https://github.com/Diftic/wingman-ai/tree/contrib/sc-navpoint) |
| Accountant | `accountant` | `d0a4dbc` | 19 | [contrib/sc-accountant](https://github.com/Diftic/wingman-ai/tree/contrib/sc-accountant) |

Run `Check.ps1 -Skill navpoint` or `Check.ps1 -Skill accountant` for the additional
branches. Each has its own `sc-<skill>.allowlist.json` and local Git hooks.

Accountant passed 58 selected ERP/domain, dashboard, and custom-loader tests.
NavPoint passed 255 runtime tests; three tests for the old release-builder
manifests were explicitly deselected because those files are intentionally not
distributed in this contribution. The selected OpenCV dependency, V8 model and
alphabet hashes, synthetic OCR inference, QR generation, and dashboard assets
were also checked. Tests ran against exact file snapshots outside the checkouts.
See `ADDITIONAL-VERIFICATION.md` for scope and test exclusions.

NavPoint includes an 82.30 MiB OpenCV native library. GitHub accepted the push
with its large-file warning. Discuss dependency packaging before seeking an
upstream merge; this Windows bundle is not a cross-platform qualification.

## Current candidate

- Checkout: `D:\PycharmProjects\wingman-contributions\checkout`
- Branch: `contrib/sc-log-reader`
- Base: ShipBit `develop`, commit `6eb31903bbcacd1a9dc15dd6734e2f132bc0b657`
- Scope: 28 explicitly selected SC Log Reader files.
- Published to the personal fork on 2026-09-21 at commit `1dc1c43`.
- Branch: https://github.com/Diftic/wingman-ai/tree/contrib/sc-log-reader
- No issue or pull request has been created; ShipBit's repository was not changed.

Your development repo and the existing Accountant and Reader worktrees were not
modified. The checkout was cloned from ShipBit, so it does not inherit your
fork's development commits. It has your fork configured as `origin`; direct
upstream pushing is disabled in this checkout.

## What is included

The registration wrapper, default configuration, reader runtime, bundled JSON,
Windows CPython 3.11 regex dependency, license/attribution files, and concise
installation/compatibility documentation. The standalone CLI, duplicate source
tree, development tests, tooling, notes, plans, reports, logs, databases, and
release ZIPs were not copied.

`sc-log-reader.allowlist.json` lists every permitted repository-relative file,
where it came from, why it is present, and its reviewed content hashes. It stays
outside the checkout, along with all preparation scripts and these instructions.

## Check the candidate

In PowerShell:

```powershell
& 'D:\PycharmProjects\wingman-contributions\Check.ps1'
git -C 'D:\PycharmProjects\wingman-contributions\checkout' diff --cached --stat
git -C 'D:\PycharmProjects\wingman-contributions\checkout' diff --cached
```

The initial candidate is now committed. To inspect its published changes, use
`git show --stat 1dc1c43` or `git show 1dc1c43` from the checkout. The staged
diff commands above show subsequent changes before they are committed.

The local pre-commit and pre-push hooks run the same checker. It checks the index,
working files, exact reviewed content, and every contribution commit. A private
file committed and then removed is still rejected. Only the configured topic
branch may be pushed to the configured fork. A plain `git push` is disabled;
publishing must be explicit. Hooks are local accident prevention and can be
bypassed; do not bypass them to resolve a rejected contribution.

Content changes require a new review and updated hashes. Do not automatically
approve every changed file or use a folder-wide wildcard. Keep new notes here,
outside `checkout`. The checker intentionally also flags ignored local output;
keep test caches and reports outside the checkout and use Python `-B` when needed.

## Updating this candidate or adding another skill

1. Keep working in the original development repo.
2. For an update, inspect the changed runtime files and copy only exact selected
   filenames into the contribution checkout. Review their content before updating
   the allowlist hashes. The preparation script is deliberately one-shot and
   refuses to overwrite an existing candidate.
3. For another skill, use another clean checkout/branch based on current ShipBit
   `develop`. Give it a separate allowlist and point its hooks at that allowlist.
   Do not branch from this Reader candidate or merge your development fork.
4. Run the guard and the relevant skill checks. Review the complete staged diff
   and contribution commit messages before publishing.
5. When publishing is requested, commit the reviewed candidate, push only its
   topic branch to your fork, and open a PR targeting ShipBit `develop`. ShipBit
   requires an associated issue. Review any updated upstream base before rebasing
   and update the allowlist's base only after that review.

## Validation and remaining work

The file guard has eight passing regression checks, including staged planning
files, unreviewed content, missing runtime files, hidden history, and wrong push
destinations. Selected Python files parse, native regex loads on Windows CPython
3.11, and the reader modules/bundled JSON load without starting Wingman.

Runtime bytes are preserved, including Windows line endings and the bundled
instruction JSON. The whitespace review has one inherited blank final line in
the third-party regex WHEEL metadata; that vendor file was kept unchanged.

This is a locally prepared contribution candidate, not a claim of compatibility
with the latest running Wingman. Before a PR, qualify it with the intended host
and check ShipBit's preferred dependency packaging. The bundled native extension
is Windows/CPython-3.11-specific; no cross-platform support is claimed.

Excluding files here does not remove anything already published on your public
fork or erase its history.
