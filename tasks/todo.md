# Aurora v22 task checklist

- [ ] Add and test dependency-free v22 core contracts.
- [ ] Ship the core package through the source installer.
- [ ] Add Unix JSON IPC and hidden daemon mode.
- [ ] Expand status JSON and agent commands.
- [ ] Integrate embedded lyrics and exponential sleep fade.
- [ ] Add light/dark/system themes and spring controls.
- [ ] Upgrade visualizer interpolation and queue drag reorder.
- [ ] Update docs and release metadata.

## Verification checkpoint

- [ ] `python3 -m py_compile aurora-player/aurora_player.py`
- [ ] `pytest -q`
- [ ] Offline CLI smoke checks pass.
