#!/usr/bin/env bash
# Render the brand SVGs in static/brand/ to the PNG icons browsers and home
# screens need (specs/004-ui-overhaul research D6). Run by hand when the logo
# changes, then commit the PNGs: nothing in the image or at runtime runs this.
#
# Why headless Chrome: nothing else on the dev Mac rasterises SVG (Homebrew's
# ffmpeg has no librsvg, and Pillow isn't installed). Adding a Python
# rasteriser to requirements.txt would put a runtime dependency in the image
# for a build-time job (constitution Principle IV).
#
#     tools/render-icons.sh
set -euo pipefail

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
BRAND="$(cd "$(dirname "$0")/../static/brand" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# render <svg> <size> <out.png> <transparent|opaque>
#
# Each SVG is wrapped in a page that draws it at exactly size x size, so the
# screenshot is the icon with no margin, scrollbar or scaling guesswork.
render() {
  local svg="$1" size="$2" out="$3" mode="$4"
  local page="$WORK/$(basename "$out" .png).html"
  cat > "$page" <<HTML
<!doctype html><html><head><style>
html,body{margin:0;padding:0;background:transparent;overflow:hidden}
img{display:block;width:${size}px;height:${size}px}
</style></head><body><img src="file://$BRAND/$svg"></body></html>
HTML
  # (expanded as ${bg[@]+...} below: macOS bash 3.2 calls an empty array unbound under set -u)
  local bg=()
  # Apple touch and maskable icons must be opaque: iOS applies its own corner
  # mask and fills any transparency with black, and Android's adaptive mask
  # expects a full-bleed square. Their SVG is full-bleed, so no background
  # shows; only the transparent ones override Chrome's default white.
  if [[ "$mode" == transparent ]]; then bg=(--default-background-color=00000000); fi
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
    --allow-file-access-from-files ${bg[@]+"${bg[@]}"} \
    --window-size="$size,$size" --screenshot="$BRAND/$out" "file://$page" >/dev/null 2>&1
  echo "rendered $out (${size}px, $mode) from $svg"
}

render mark-small.svg    32  favicon-32.png         transparent
render mark.svg          192 icon-192.png           transparent
render mark.svg          512 icon-512.png           transparent
render mark-maskable.svg 180 apple-touch-icon.png   opaque
render mark-maskable.svg 512 icon-maskable-512.png  opaque
