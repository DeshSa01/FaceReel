# Design Tokens Contract: Supercut

The one source of visual values (FR-007). It is defined once, at the top of
`static/css/supercut.css`. No page may declare a colour, radius, shadow, font size or
duration that is not one of these tokens.

Colours use `light-dark(<light>, <dark>)` (research D2). Contrast for every text and
control pair is measured by [`../contrast.py`](../contrast.py), and every pair passes
(research D3). A change to any colour here MUST be followed by re-running it.

## Colour

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F6F6FA` | `#0A0A10` | page background |
| `--surface` | `#FFFFFF` | `#13131C` | cards, header, bar |
| `--raised` | `#EFEFF5` | `#1B1B27` | inputs, hovered rows, chips |
| `--media` | `#0A0A10` | `#000000` | behind video, thumbnails, previews (no halo in dark) |
| `--text` | `#15151F` | `#ECECF4` | body text |
| `--muted` | `#585870` | `#A3A3BA` | secondary text, hints |
| `--border` | `#E2E2EB` | `#272735` | decorative hairlines only (not a control's sole boundary) |
| `--control` | `#8A8AA3` | `#6C6C88` | input, toggle and slider-track boundaries (≥ 3:1) |
| `--accent` | `#5B3DF5` | `#6A50FA` | primary fills, focus, active nav |
| `--accent-text` | `#5B3DF5` | `#A996FF` | links and accent-coloured text |
| `--on-accent` | `#FFFFFF` | `#FFFFFF` | text on `--accent` |
| `--coral` | `#E5306F` | `#FF5C93` | **decoration only**: gradient end, particles. Never text, never behind text. |
| `--success` | `#0A7350` | `#3DD68C` | done |
| `--warning` | `#9A5200` | `#F5A524` | network wait, "finishes after current" |
| `--danger` | `#C8243C` | `#FF6B7D` | failed, destructive actions |
| `--focus` | `= --accent` | `#A996FF` | 2px focus ring |
| `--gradient` | `linear-gradient(135deg, #5B3DF5, #E5306F)` | `linear-gradient(135deg, #6A50FA, #FF5C93)` | logo tile, progress fills, celebration, reel presenter frame |

Tinted status backgrounds (badge fills) are each status colour at 12% (light) or 18%
(dark) over `--surface`, via `color-mix(in oklab, var(--success) 12%, var(--surface))`.
The badge's text uses the full status colour. Tints are measured directly by
`contrast.py`, not inferred from the `--raised` result: the narrowest, light danger on
its tint, is 4.70:1. Light `--success` was darkened from `#0B7A54` to `#0A7350` after it
measured only 4.54:1 on its tint.

Input placeholder text uses `--muted` at full opacity, never reduced opacity, which
would drop it below 4.5:1.

## Type

| Token | Value |
|---|---|
| `--font` | `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` |
| `--font-mono` | `ui-monospace, "SF Mono", Menlo, Consolas, monospace` |
| `--fs-xs` / `--fs-sm` / `--fs-md` / `--fs-lg` / `--fs-xl` / `--fs-2xl` / `--fs-3xl` | 0.75 / 0.875 / 1 / 1.25 / 1.563 / 1.953 / 2.441 rem (1.250 scale) |
| `--fw-regular` / `--fw-semibold` / `--fw-bold` / `--fw-black` | 450 / 600 / 750 / 800 |
| `--tracking-tight` | `-0.02em` (`--fs-xl` and up) |
| `--lh-tight` / `--lh-body` | 1.2 / 1.55 |

All changing numbers use `font-variant-numeric: tabular-nums`.

## Space, shape, depth

| Token | Value |
|---|---|
| `--s-1` … `--s-8` | 4, 8, 12, 16, 24, 32, 48, 64 px |
| `--r-sm` / `--r-md` / `--r-lg` / `--r-xl` / `--r-full` | 6 / 10 / 14 / 20 px / 999px |
| `--shadow-1` | light `0 1px 2px rgb(20 20 40 / .06), 0 1px 1px rgb(20 20 40 / .04)`; dark `0 0 0 1px rgb(255 255 255 / .04)` |
| `--shadow-2` | light `0 8px 24px -8px rgb(20 20 40 / .18)`; dark `0 12px 32px -8px rgb(0 0 0 / .6), 0 0 0 1px rgb(255 255 255 / .05)` |
| `--glow` | `0 0 0 1px color-mix(in oklab, var(--accent) 40%, transparent), 0 8px 32px -8px color-mix(in oklab, var(--accent) 50%, transparent)`: the finished-reel presenter and the active stage |
| `--content-max` | 1120px (archive), 960px (session, two-column at ≥ 960px), 720px (home) |
| `--tap-min` | 44px under `(pointer: coarse)`, 32px otherwise |

Dark-theme shadows switch to a hairline ring. Drop shadows are invisible on near-black
and turn into muddy halos.

## Motion

All transitions and animations sit inside `@media (prefers-reduced-motion:
no-preference)` (research D15). These values are chosen, not measured.

| Token | Value | Use |
|---|---|---|
| `--ease-out` | `cubic-bezier(.2, .8, .2, 1)` | entrances |
| `--ease-spring` | `cubic-bezier(.34, 1.56, .64, 1)` | badges, the presenter pop |
| `--t-fast` / `--t-med` / `--t-slow` | 120 / 220 / 400 ms | hover, state change, presenter entrance |
| celebration | ≤ 1600 ms total, about 36 particles | research D12 |
| hover-preview delay | 250 ms | avoids starting a video fetch while the pointer sweeps across the grid |
| hover-preview length | first 6 s, looped | long enough to recognise the reel; bounds the bytes fetched per hover |
