# Local contribution preparation

- The user wants to share only the skill files required for a useful contribution.
- Keep development notes, handovers, manifests, checks, and preparation tooling
  outside the `checkout`, `navpoint`, and `accountant` Git directories. Never add
  them to contribution commits.
- Preserve `D:\PycharmProjects\wingman-ai` and its existing worktrees. Read them
  only unless the user explicitly requests development changes there.
- Start each skill contribution from ShipBit `develop`, never from the personal
  fork's development branch or another skill contribution branch.
- Use exact file allowlists, not extension filters or recursive directory copies.
- Review runtime dependencies, required assets, licenses, and minimal usage docs.
  Existing source code can contain private material too: inspect selected content.
- `sc-log-reader.allowlist.json`, `sc-navpoint.allowlist.json`, and
  `sc-accountant.allowlist.json` are the local policies for their respective candidates.
  It records the pinned base, branch, destination, source paths, and file hashes.
  Do not refresh hashes automatically to make a check pass. Review changes first.
- Run `Check.ps1 -Skill log-reader|navpoint|accountant` after changes. Do not bypass hooks. Keep verification output
  outside the checkout. Checks cover file contents and all intermediate commits;
  separately review commit messages before publishing.
- This setup is not standing authorization to publish future changes. The user
  explicitly authorized pushing the three current contributions to the personal
  fork. No issue or pull request has been opened. Follow subsequent user scope.
- Other skill candidates need their own branch, manifest, and hook configuration.
- Runtime/host qualification is separate from successful file-scope validation.
