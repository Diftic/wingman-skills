# NavPoint and Accountant contribution verification — 2026-09-21

Source development files were read only. Exact selected files were copied into
independent clean clones of ShipBit develop at
`6eb31903bbcacd1a9dc15dd6734e2f132bc0b657`. Allowlist checks verify staged,
working-tree, and committed content hashes and reject unrelated files/history.
Both contribution commits passed their installed pre-commit and pre-push guards.

## Accountant

- Branch `contrib/sc-accountant`, commit `d0a4dbc`, 19 files.
- 58 tests passed from `test_erp.py`, `test_erp_web.py`, and
  `test_erp_host_contract.py` against the selected runtime snapshot.
- QR PNG generation and dashboard asset existence passed.
- Legacy implementations, old dashboard assets (except its required QR helper),
  installers, standalone launcher, notes, reports, and player databases excluded.
- The selected tests use temporary databases and FastAPI TestClient. The loader
  contract test uses a host stand-in; this is not live Wingman qualification.
- Results: `validation/accountant-99236d6a/pytest.txt` and `smoke.txt`.

## NavPoint

- Branch `contrib/sc-navpoint`, commit `fc8727c`, 53 files.
- 255 runtime tests passed. Real selected OpenCV imports and resizes correctly,
  including when the legacy NumPy alias is absent. The V8 model/alphabet hashes
  pass and the selected ONNX model executes on synthetic input. QR PNG generation
  passes. No game was launched or screen captured.
- Initial test collection lacked the existing Wingman host stand-ins; copying
  the development `_stubs.py` into the private test snapshot fixed that setup.
  A missing shared fixture module was also added to the private test snapshot.
- Three old release-tooling tests failed because they require the intentionally
  excluded `update_release.py` and `skill_installer_config.json`. They were
  explicitly deselected in the final runtime test run:
  - `test_the_new_runtime_module_is_in_both_release_manifests`
  - `test_the_two_release_manifests_agree`
  - `test_every_flat_runtime_import_of_main_is_released`
- Their contribution file-scope role is handled by the new external allowlist
  guard; the reduced runtime itself is imported/exercised by the selected tests.
- Private test snapshot: `validation/navpoint-3aadc662`.
  Its `pytest.txt` records the earlier run; `pytest-final.txt` records the final
  255-pass, 3-deselected result.
- Old releases, notes, training/export reports, provenance inventories, typing
  stubs, and the unused FFmpeg video plugin were excluded. License notices and
  a concise OpenCV loader-modification notice are included.
- GitHub accepted the 82.30 MiB native OpenCV file with a large-file warning.

## Limits

These are focused package/runtime checks, not either project's full historical
suite, a complete security/privacy audit, or live-host/game qualification.
No product behavior or original development code was modified. The only newly
authored contribution files are concise usage and dependency-attribution docs.
No tests, test output, local controls, or planning files were pushed.
