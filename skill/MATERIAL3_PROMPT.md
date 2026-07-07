# MATERIAL 3 IMPLEMENTATION PROMPT — Aurora Music Player

> Agent prompt: how Material 3 was implemented in Aurora v12.3, and how to
> extend or re-theme it. Give this file to any agent that must modify the
> player's UI. **Status: IMPLEMENTED in aurora_player.py v12.3.**

## Mission

Apply Google's **Material 3 design system** to Aurora Music Player.

References:
- https://github.com/devrath/Material-3-Design-Kit (Compose component kit)
- https://developer.android.com/develop/ui/compose/designsystems/material3
- https://m3.material.io (spec: color roles, type scale, shape scale, states)

Aurora is **Python + PySide6 (Qt)**, not Android/Jetpack Compose. So M3 is
implemented by **translating the design system, not the framework**:
M3 tokens → a Python dict → Qt Style Sheets (QSS). Never port Compose code.

## Architecture (already in aurora_player.py)

1. **`M3` dict** — Material 3 *color roles*, dark scheme generated from seed
   `#6366F1` (Aurora indigo). Keys mirror Compose `MaterialTheme.colorScheme`
   (`primary`, `on_primary`, `primary_container`, `surface_container_high`,
   `outline_variant`, …).
2. **`_rgba(hex, a)` / `_mix(base, layer, t)`** — helpers that precompute M3
   **state layers** (QSS has no overlay compositing): hover = 8%, press = 12%
   of the content color over its container.
3. **`_m3ss(qss)`** — substitutes `@token` placeholders in the stylesheet with
   `M3[...]` values (longest-token-first so `@primary_container` isn't eaten
   by `@primary`).
4. **`SS`** — the master stylesheet: every Qt widget rule is mapped to an M3
   component + tokens. Applied once via `app.setStyleSheet(SS)`.
5. Icons: `_svg()` defaults to `on_surface_variant`; content on colored
   containers must pass an explicit `on_*` token (e.g. the play FAB icon uses
   `on_primary_container`).

## Compose → Qt component mapping

| Material 3 component (Compose)       | Aurora widget            | Tokens |
|--------------------------------------|--------------------------|--------|
| `NavigationDrawer`                   | `QFrame#sidebar`         | `surface_container_low` |
| `NavigationDrawerItem` (active pill) | `QPushButton#navButton`  | checked: `secondary_container` / `on_secondary_container`, radius 24 pill |
| `BottomAppBar`                       | `QFrame#playerBar`       | `surface_container` |
| `FloatingActionButton` (56dp, 16dp corner) | `QPushButton#playButton` | `primary_container` / `on_primary_container` |
| `IconButton` (standard, 40dp circle) | `QPushButton#controlButton` | transparent + state layers; **checked = tonal**: `secondary_container` |
| `Button` (filled)                    | `QPushButton#createBtn`, dialog Test btn | `primary` / `on_primary`, full pill |
| `FilledTonalButton`                  | dialog Select btn        | `secondary_container` / `on_secondary_container` |
| `SearchBar` (full pill)              | `QLineEdit#searchBar`    | `surface_container_high`, radius 24 |
| `OutlinedTextField` / dropdown       | `QComboBox#sortCombo`    | border `outline`, radius 4 |
| `Slider`                             | `QSlider` seek/volume    | active `primary`, inactive `surface_container_highest` |
| `ListItem` (selected)                | `QListWidget::item`      | hover: 8% `on_surface` layer; selected: `secondary_container` |
| `DropdownMenu`                       | `QMenu`                  | `surface_container`, radius 4 |
| `PlainTooltip`                       | `QToolTip`               | `inverse_surface` / `inverse_on_surface` |
| Dialog (`AlertDialog`)               | device selector `QDialog`| `surface_container_high` |

## Type scale used (M3 → px)

- headline-large 32/400 → `pageTitle`
- title-large 22/400 → `queueHeader`
- title-medium 16/500 → `titleLabel`
- title-small 14/500 → `sidebarHeader`
- body-large 14 → base font
- body-medium 14 → subtitles/artist
- label-large 14/500 → buttons, nav items
- label-small 11/500 → time labels

## Hard rules

1. **Never hard-code a hex color** in widget code or inline
   `setStyleSheet`. Always use `M3['...']` (f-string) or `_m3ss("""...@token...""")`.
2. **Pairs stay paired**: content on `X` must be `on_X`
   (`primary_container` → `on_primary_container`). Never mix groups.
3. **State layers**: hover 8%, press 12% of the *content* color. Use
   `state_hover_on_surface` / `state_press_on_surface` on neutral surfaces,
   or the precomputed `*_hover` / `*_press` tokens on colored containers.
4. **Qt radius gotcha**: QSS ignores `border-radius` > half the widget
   height. For pills, radius ≤ height/2 (navButton uses 24 with min-height
   guaranteeing ≥48px). Don't blindly write 28.
5. **`QLabel { background:transparent; }` must stay** — otherwise labels
   paint opaque `surface` boxes on top of container-colored bars.
6. Elevation: M3 dark uses **tonal color, not shadows** — deeper layers use
   `surface_container_low(est)`, raised layers `surface_container_high(est)`.
   Do not add drop shadows.
7. Icon buttons are ≥40×40 (M3 touch target). Don't shrink below that.

## To re-theme (new seed color)

1. Generate a tonal palette for the new seed (Material Theme Builder:
   https://material-foundation.github.io/material-theme-builder/).
2. Replace only the hex values in the `M3` dict — dark scheme mapping:
   primary=P-80, on_primary=P-20, primary_container=P-30,
   on_primary_container=P-90; surfaces = neutral tones 4–22.
3. Touch nothing else. The stylesheet, state layers, and inline styles all
   derive from the dict.

## Verify after any change

```bash
python3 -m py_compile aurora_player.py          # syntax
QT_QPA_PLATFORM=offscreen python3 aurora_player.py --version
aurora-player   # visual: pill nav active state, FAB play button,
                # search pill, slider colors, list selection, no black
                # label boxes in the player bar
```
