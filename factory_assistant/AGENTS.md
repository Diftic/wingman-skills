# Project instructions

- This is Factory Assistant, developed in `D:\PycharmProjects\wingman-ai\skills\factory_assistant`. It is built from Satisfactory Assistant 0.9.1.
- Do not change `skills/satisfactory_assistant`. It is the reference and the working fallback.
- There is only ONE Orchestrator (`main.py`, `factory_orchestrator/`). Each game has its own Reader (`factory_games/<game>/reader`) and Handler (`factory_games/<game>/handler` + `game.py`).
- User terminology (same as SC Log Reader): Reader = save/catalog interpretation, Handler = game logic and state, Orchestrator = Wingman settings, tools and lifecycle.
- Read `ARCHITECTURE.md` before you change code. Keep `tests/test_layer_boundaries.py` green.
- Never put game-specific code or game names in `main.py`, `factory_orchestrator/` or `factory_shared/`.
