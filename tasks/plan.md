# Implementation Plan: Aurora Music Player v22.0.0

## Overview

Upgrade the existing lightweight PySide6 player in focused slices while keeping
the current single-process GUI and backwards-compatible CLI. New pure-Python
core modules will hold queue, lyrics, theme, DSP, telemetry, IPC, and stream
contracts so they can be tested without starting Qt or a desktop session.

## Architecture Decisions

- Keep `aurora_player.py` as the launch point and preserve existing command
  names; install the new `aurora_core/` package beside it.
- Use a Unix-domain JSON-lines socket for reliable headless IPC, retaining the
  command-file transport as a compatibility fallback.
- Keep playback on Qt Multimedia. The EQ module exposes a dependency-light
  10-band DSP processor and the UI/telemetry use the same validated gains;
  Qt's player remains the low-overhead playback backend.
- Make telemetry a versioned, additive JSON contract: existing top-level keys
  remain available while v22 fields are added.
- Prefer bounded timers and lazy imports so the idle process remains suitable
  for low-end Linux hardware.

## Task List

### Phase 1: Foundation

- [ ] Task 1: Add pure v22 core contracts for queue ordering, lyrics parsing,
  theme contrast, EQ validation/DSP, telemetry, and stream strategies.
- [ ] Task 2: Add focused pytest coverage for those contracts and update the
  installer/package metadata to ship the core package.

### Checkpoint: Foundation

- [ ] `python3 -m py_compile aurora-player/aurora_player.py`
- [ ] Focused and full pytest runs pass.
- [ ] Existing `--version`, `--help`, and offline playlist commands still work.

### Phase 2: Agent and Playback Core

- [ ] Task 3: Replace file-only IPC as the primary transport with Unix-socket
  JSON IPC, add hidden `--daemon` startup, and retain the fallback path.
- [ ] Task 4: Integrate v22 telemetry fields, stream resolver status, EQ state,
  queue position, buffer health, and new agent commands.
- [ ] Task 5: Add embedded USLT/plain lyrics precedence and correct exponential
  sleep fade/end-of-song behavior.

### Checkpoint: Core Features

- [ ] Socket commands are acknowledged and delivered on the Qt main thread.
- [ ] `--status` contains duration, bitrate, buffer health, queue position, and
  EQ preset fields.
- [ ] Offline metadata/lyrics/EQ/queue checks pass without network access.

### Phase 3: Expressive UI

- [ ] Task 6: Add WCAG-conscious light/dark/system palette switching and
  expressive spring-style control micro-interactions.
- [ ] Task 7: Upgrade the visualizer to 60fps interpolation with configurable
  color schemes and expose drag-and-drop queue reordering.
- [ ] Task 8: Update v22 documentation, help text, version metadata, and release
  notes.

### Checkpoint: Complete

- [ ] Syntax verification and all repository tests pass.
- [ ] GUI construction smoke test succeeds when PySide6/display support exists.
- [ ] Git history contains focused descriptive commits for each progressive
  improvement.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| PySide6 is unavailable in CI/headless environments | High | Keep core modules dependency-free and make Qt checks conditional. |
| Qt Multimedia has no portable post-decode filter hook | High | Isolate DSP math in a reusable processor and keep playback stable; expose its state in the agent contract. |
| Socket and legacy file IPC race during upgrades | Medium | Socket is preferred, file transport remains a fallback, and stale sockets are removed safely. |
| Theme overrides contain legacy hard-coded dark colors | Medium | Replace structural backgrounds with palette tokens where they affect light mode. |
| Low-end CPU budget | Medium | Lazy imports, bounded FFT rate, interpolation in the paint timer, and no new always-on workers. |

## Open Questions

- None blocking implementation. The existing Qt Multimedia backend is retained
  for compatibility and low memory use.
