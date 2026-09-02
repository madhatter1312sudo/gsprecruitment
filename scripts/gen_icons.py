#!/usr/bin/env python3
"""Regenerate GSP's square touch/PWA icons from the master lockup source.

Run from the repo root:
    python3 scripts/gen_icons.py

Source: scripts/assets/gsp_logo_full.png (the full "GSP RECRUITMENT" lockup,
white background, gold mark on the left). This is a build-time design
source, not a served web asset, so it lives under scripts/, not website/.

What it does:
1. Crops the square gold symbol out of the lockup (cols 0-299, full height).
2. Decontaminates the anti-aliased edge pixels: the source has the symbol
   blended against solid white, so per-pixel alpha (gold coverage) is
   recovered from the blue channel, which is ~0 for gold and 255 for white
   -- the channel with the cleanest separation between the two colors.
3. Premultiplied-resizes that alpha-mask to each target size (avoids the
   light/white fringe that naive straight-alpha resizing produces).
4. Composites the result onto an OPAQUE navy (#0A1628) background and writes
   fully opaque PNGs -- iOS composites transparent apple-touch-icons onto a
   black background, so these must not carry transparency.

Outputs (into website/, overwriting in place):
    apple-touch-icon.png  180x180  opaque navy background
    icon-192.png           192x192  opaque navy background
    icon-512.png           512x512  opaque navy background

favicon-16/32/64.png and favicon.ico are hand-authored, stay transparent,
and are NOT touched by this script.
"""

import os
from PIL import Image

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(REPO_ROOT, "scripts", "assets", "gsp_logo_full.png")
WEBSITE = os.path.join(REPO_ROOT, "website")

GOLD = (250, 206, 0)
NAVY = (10, 22, 40)  # #0A1628, --navy-800 in website/theme.css

# Symbol bounding box within the lockup source (found by column-scan: the
# symbol spans x 0-299 before a blank gap, then the "GSP" wordmark starts).
CROP_BOX = (0, 0, 300, 299)

SIZES = {
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}


def decontaminate_alpha(rgb_im):
    """Build an RGBA image with the gold color and a recovered coverage
    alpha, from an RGB crop that has the symbol anti-aliased against solid
    white. Uses the blue channel (gold blue ~= 0, white blue = 255) as the
    alpha estimator -- the channel with the largest gap between the two
    source colors, so it's the most robust to compression noise.
    """
    rgb_im = rgb_im.convert("RGB")
    w, h = rgb_im.size
    px = rgb_im.load()
    out = Image.new("RGBA", (w, h))
    opx = out.load()
    white_b = 255
    gold_b = GOLD[2]
    span = white_b - gold_b  # 255
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            alpha = (white_b - b) / span
            alpha = max(0.0, min(1.0, alpha))
            a = round(alpha * 255)
            opx[x, y] = (GOLD[0], GOLD[1], GOLD[2], a)
    return out


def premultiplied_resize(rgba_im, size):
    """Resize with premultiplied alpha so edges don't pick up a light/white
    fringe from the fully-transparent neighboring pixels."""
    pm = rgba_im.convert("RGBa")
    pm = pm.resize((size, size), Image.LANCZOS)
    return pm.convert("RGBA")


def composite_opaque(rgba_im, bg_rgb):
    """Flatten rgba_im onto a solid opaque background, returned as RGBA
    with alpha forced to 255 everywhere (verifiably fully opaque)."""
    w, h = rgba_im.size
    bg = Image.new("RGBA", (w, h), bg_rgb + (255,))
    flat = Image.alpha_composite(bg, rgba_im)
    r, g, b, a = flat.split()
    a = a.point(lambda _: 255)
    return Image.merge("RGBA", (r, g, b, a))


def main():
    src = Image.open(SOURCE)
    crop = src.crop(CROP_BOX)
    w, h = crop.size
    side = max(w, h)
    padded_rgb = Image.new("RGB", (side, side), (255, 255, 255))
    padded_rgb.paste(crop, ((side - w) // 2, (side - h) // 2))

    master_rgba = decontaminate_alpha(padded_rgb)

    for name, size in SIZES.items():
        resized = premultiplied_resize(master_rgba, size)
        opaque = composite_opaque(resized, NAVY)
        out_path = os.path.join(WEBSITE, name)
        opaque.save(out_path)
        alpha_min = min(opaque.split()[-1].getdata())
        print(f"{name}: {opaque.size} {opaque.mode} alpha_min={alpha_min}")


if __name__ == "__main__":
    main()
