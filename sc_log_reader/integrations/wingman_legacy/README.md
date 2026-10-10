# Legacy Wingman adapter — development only

Historical integration template. The 0.4.0 candidate uses the inspected development 3.1.2 source contract and staged registration in [wingman_target](../wingman_target/CONTRACT.md). Reader/Handler/Orchestrator implementation and standalone lifetime ownership are accepted, with 50 ms operation/100 ms shared parse bounds. Final archive comparisons are complete; local paced/recovery qualification is complete and final local artifacts are prepared for controller binding/review. Actual host/native settings action/frozen runtime are unqualified.

`src/sc_log_reader/main.py` exports `SCLogReader(Skill)` for the local legacy constructor `Skill(config, settings, wingman)`. `default_config.yaml` is its settings template.

This project has not modified or installed into Wingman. A maintainer would need to make this package and its `regex` dependency importable by the target Wingman runtime, register the skill using the template, and point it at a separate writable runtime directory. Do that in an isolated Wingman test installation first.

The inspected source constructor/prepare/unload/tools boundary is exercised with host doubles and isolated native candidates. Actual Wingman loading, GUI rendering and shutdown remain unqualified; public 2.x/general API 3 support is not claimed.

Settings:

- **Star Citizen Path:** parent containing LIVE, PTU, etc.
- **Runtime Directory:** dedicated local database/update folder. Use this same path with CLI `check`, `status`, `approve` and `rollback`.
- **Instruction Update URL:** optional direct HTTPS raw GitHub JSON URL.
- **React to Game Events:** the current master toggle defaults off; seven category toggles default on under it. Enabled presentation uses bounded literal GUI transport with rate/repeat/catch-up suppression. No TTS or command-pipeline reaction is implemented.

Automatic update checks run at startup and every six hours. The user reviews version/release notes/compatibility and exact digest in the local window or CLI. Approval is manual and binds the displayed digest. The current source-host integration writes an exact-interpreter/exact-runtime human review launcher; the inspected host has no native settings action API. Native settings integration, actual host registration/install and frozen launcher remain maintainer/qualification work.

`get_reader_health` exposes parsing diagnostics, freshness, backlog, detected build and worker errors. Source-time environment selection is not proof that an environment is currently running. Keep one monitoring instance per runtime directory; the manual update window/CLI can run alongside it. Tests cover worker exceptions, poisoned records, hidden review-window interaction and bounded unload using a host double.

No donation/upload implementation is included. Do not register the old and new versions under the same module/name or let them share a runtime database.
