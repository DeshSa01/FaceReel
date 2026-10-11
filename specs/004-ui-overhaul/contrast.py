"""WCAG 2.1 contrast ratios for the design tokens (research D3).

Re-run after changing any colour in contracts/design-tokens.md or
static/css/supercut.css; every pair below must meet its "need" value.

    python3 specs/004-ui-overhaul/contrast.py

Covers the token pairs, the tinted status-badge fills (status colour mixed
into --surface in oklab, exactly as CSS color-mix() does), and input
placeholder text (--muted on --raised).
"""

def _lum(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    hi, lo = sorted([_lum(a), _lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- color-mix(in oklab, A p%, B), for the badge tints -----------------------

def _s2l(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _l2s(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _to_oklab(h):
    h = h.lstrip("#")
    r, g, b = (_s2l(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    return (0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s)


def _from_oklab(L, a, b):
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    return "#" + "".join(f"{round(min(1, max(0, _l2s(x))) * 255):02X}" for x in rgb)


def mix(a, p, b):
    pa, pb = _to_oklab(a), _to_oklab(b)
    return _from_oklab(*(p * x + (1 - p) * y for x, y in zip(pa, pb)))


THEMES = {
    "light": dict(bg="#F6F6FA", surface="#FFFFFF", raised="#EFEFF5", text="#15151F",
                  muted="#585870", control="#8A8AA3", accent_text="#5B3DF5",
                  accent_fill="#5B3DF5", success="#0A7350", warning="#9A5200",
                  danger="#C8243C", tint=0.12),
    "dark": dict(bg="#0A0A10", surface="#13131C", raised="#1B1B27", text="#ECECF4",
                 muted="#A3A3BA", control="#6C6C88", accent_text="#A996FF",
                 accent_fill="#6A50FA", success="#3DD68C", warning="#F5A524",
                 danger="#FF6B7D", tint=0.18),
}

# (foreground token, background token, minimum ratio)
PAIRS = [(fg, bg, 4.5) for fg in ("text", "muted", "accent_text", "success", "warning", "danger")
         for bg in ("bg", "surface", "raised")]
PAIRS += [("control", "bg", 3.0), ("control", "surface", 3.0), ("accent_fill", "surface", 3.0)]
STATUS = ("success", "warning", "danger", "accent_text")

failed = 0


def check(label, fg, bg, need):
    global failed
    r = ratio(fg, bg)
    ok = r >= need
    failed += not ok
    print(f"  {'ok  ' if ok else 'FAIL'} {label:34} {r:5.2f}  (need {need})")


for name, t in THEMES.items():
    print(f"== {name}")
    for fg, bg, need in PAIRS:
        check(f"{fg} on {bg}", t[fg], t[bg], need)
    check("white on accent_fill", "#FFFFFF", t["accent_fill"], 4.5)
    # placeholder text is --muted on an input's --raised fill (covered above,
    # restated so the rule "placeholders use --muted, never opacity" is checked)
    check("placeholder (muted) on raised", t["muted"], t["raised"], 4.5)
    for k in STATUS:
        tint = mix(t[k], t["tint"], t["surface"])
        check(f"{k} on its badge tint {tint}", t[k], tint, 4.5)
raise SystemExit(1 if failed else 0)
