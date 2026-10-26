# Aurora v22 task checklist

- [x] Add and test dependency-free v22 core contracts.
- [x] Ship the core package through the source installer.
- [x] Add Unix JSON IPC and hidden daemon mode.
- [x] Expand status JSON and agent commands.
- [x] Integrate embedded lyrics and exponential sleep fade.
- [x] Add light/dark/system themes and spring controls.
- [x] Upgrade visualizer interpolation and queue drag reorder.
- [x] Update docs and release metadata.

## Verification checkpoint

- [x] `python3 -m py_compile aurora-player/aurora_player.py`
- [x] `pytest -q`
- [x] Offline CLI smoke checks pass.
