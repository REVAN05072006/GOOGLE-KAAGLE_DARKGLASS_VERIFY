# captcha_generator.py
"""
Enhanced CAPTCHA media renderer.

Provides:
 - create_image_from_description(description, width, height, seed)
     Renders noisy images that may contain text (word-based) or decorative patterns.
     If the AI description implies a click-point solution, it will NOT guess the solution;
     the server rendering is only visual. The canonical solution must come from the AI.
 - create_color_image(color_rgb, width, height, seed)
     Renders a simple colored rectangle with optional pattern/noise and returns a PNG data URI.
 - create_audio_from_text(text, lang)
     Uses gTTS (unchanged) to synthesize audio and return a data URI (mp3).
 - prepare_pattern_ui(shapes, seed)
     Returns a shapes list and a hint; client renders a clickable sequence UI.
"""

import io
import base64
import random
import math
from typing import Tuple, List, Dict, Any
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS

# helper: small palette-to-name mapping for color captchas (common colors)
_COMMON_COLOR_NAMES = {
    (255, 0, 0): "red",
    (0, 255, 0): "green",
    (0, 0, 255): "blue",
    (255, 255, 0): "yellow",
    (255, 165, 0): "orange",
    (128, 0, 128): "purple",
    (255, 192, 203): "pink",
    (0, 0, 0): "black",
    (255, 255, 255): "white",
    (128, 128, 128): "gray",
    (165, 42, 42): "brown",
    (0, 255, 255): "cyan",
    (0, 128, 0): "darkgreen",
    (75, 0, 130): "indigo",
}

def pil_to_data_uri(img: Image.Image, fmt="PNG") -> str:
    buffered = io.BytesIO()
    img.save(buffered, format=fmt)
    b64 = base64.b64encode(buffered.getvalue()).decode("ascii")
    if fmt.upper() == "PNG":
        return f"data:image/png;base64,{b64}"
    elif fmt.upper() in ("MP3", "MPEG"):
        return f"data:audio/mpeg;base64,{b64}"
    else:
        return f"data:application/octet-stream;base64,{b64}"

def mp3_bytes_to_data_uri(mp3_bytes: bytes) -> str:
    b64 = base64.b64encode(mp3_bytes).decode("ascii")
    return f"data:audio/mpeg;base64,{b64}"

def _random_font(size=32):
    # Try some common font names; fallback to default
    possible = ["arial.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    for p in possible:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

# ---------------------------
# Image renderer (word or decorative)
# ---------------------------
def create_image_from_description(description: str, width=420, height=200, seed=None) -> str:
    """
    Render an image that matches a textual description enough to be human-usable.
    NOTE: The authoritative captcha 'solution' must be supplied by the AI model (gemini_client).
    This renderer focuses on producing varied visual artifacts: words (distorted), random shapes,
    background noise, and optional "markers" (rings) if description hints at a target point.
    """
    rnd = random.Random(seed)
    # pick a dark-to-mid background
    bg = (rnd.randint(10,80), rnd.randint(10,80), rnd.randint(10,80))
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)

    # background texture: wavy lines + specks
    for _ in range(18):
        x0 = rnd.randint(-20, width + 20)
        y0 = rnd.randint(-20, height + 20)
        x1 = rnd.randint(-20, width + 20)
        y1 = rnd.randint(-20, height + 20)
        color = (rnd.randint(40,140), rnd.randint(40,140), rnd.randint(40,140))
        draw.line([x0, y0, x1, y1], fill=color, width=rnd.randint(1,3))

    for _ in range(12):
        x = rnd.randint(0, width)
        y = rnd.randint(0, height)
        r = rnd.randint(6, 28)
        outline = (rnd.randint(40,120), rnd.randint(40,120), rnd.randint(40,120))
        draw.ellipse([x-r, y-r, x+r, y+r], outline=outline)

    # parse description: detect quoted word or last alpha token
    import re
    word = None
    m = re.search(r"'([^']+)'", description)
    if m:
        word = m.group(1)
    else:
        toks = re.findall(r"[A-Za-z0-9]+", description)
        if toks:
            # often descriptions include many tokens; pick a short token likely to be a word
            word = max(toks, key=lambda t: (1.0 / (len(t) + 0.1)) if len(t) <= 8 else 0)  # bias short words

    # If the description contains "point" or "click" we add a subtle marker (visual only)
    wants_marker = bool(re.search(r"\b(click|point|ring|marker|dot|target)\b", description, re.I))

    if word:
        # Draw jittered, rotated characters with variable fonts and sizes
        cx = width // 8 + rnd.randint(-20, 20)
        # reduce word length to reasonable size
        wword = str(word)[:10]
        for ch in wword:
            fsize = rnd.randint(28, 48)
            font = _random_font(fsize)
            w, h = draw.textsize(ch, font=font)
            # place char on its own small image, rotate, then paste
            char_img = Image.new("RGBA", (w*3, h*3), (0,0,0,0))
            cd = ImageDraw.Draw(char_img)
            fill = (rnd.randint(180,255), rnd.randint(180,255), rnd.randint(180,255))
            cd.text((w, h), ch, font=font, fill=fill)
            rot = char_img.rotate(rnd.randint(-50, 50), resample=Image.BICUBIC, expand=1)
            # y position jitter
            y = (height - h) // 2 + rnd.randint(-14, 14)
            try:
                img.paste(rot, (cx, y), rot)
            except Exception:
                img.alpha_composite(rot, dest=(cx, y))
            cx += int(w * (0.8 + rnd.random() * 0.6))

        # add crossing lines and blur to make OCR harder
        for _ in range(3 + rnd.randint(0,2)):
            x0 = rnd.randint(0, width)
            y0 = rnd.randint(0, height)
            x1 = rnd.randint(0, width)
            y1 = rnd.randint(0, height)
            draw.line([x0,y0,x1,y1], fill=(rnd.randint(80,200), rnd.randint(80,200), rnd.randint(80,200)), width=rnd.randint(1,3))
        img = img.filter(ImageFilter.GaussianBlur(radius=rnd.choice([0.5, 0.8, 1.0])))
    else:
        # purely decorative: random shapes and translucent polygons
        for i in range(6):
            shape_type = rnd.choice(["ellipse", "rect", "polygon"])
            if shape_type == "ellipse":
                x = rnd.randint(20, width-20)
                y = rnd.randint(20, height-20)
                r = rnd.randint(14, 50)
                fill = (rnd.randint(100,240), rnd.randint(100,240), rnd.randint(100,240))
                draw.ellipse([x-r,y-r,x+r,y+r], fill=fill, outline=None)
            elif shape_type == "rect":
                x0 = rnd.randint(0, width//2)
                y0 = rnd.randint(0, height//2)
                x1 = x0 + rnd.randint(40, width//2)
                y1 = y0 + rnd.randint(30, height//2)
                fill = (rnd.randint(80,220), rnd.randint(80,220), rnd.randint(80,220))
                draw.rectangle([x0,y0,x1,y1], fill=fill)
            else:
                pts = [(rnd.randint(0,width), rnd.randint(0,height)) for _ in range(3 + rnd.randint(0,3))]
                draw.polygon(pts, fill=(rnd.randint(80,220), rnd.randint(80,220), rnd.randint(80,220)))

        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))

    # If marker desired, draw a faint ring at a random-ish location to hint a point without revealing exact coordinates.
    marker_info = None
    if wants_marker:
        mx = rnd.randint(int(width*0.2), int(width*0.8))
        my = rnd.randint(int(height*0.15), int(height*0.85))
        # subtle ring
        r = rnd.randint(8, 18)
        ring_color = (rnd.randint(200,255), rnd.randint(200,255), rnd.randint(200,255))
        draw.ellipse([mx-r, my-r, mx+r, my+r], outline=ring_color, width=2)
        # return marker coords in metadata if desired (but authoritative sol must come from AI)
        marker_info = {"approx_x": mx, "approx_y": my, "radius": r}

    return pil_to_data_uri(img)

# ---------------------------
# Color box renderer
# ---------------------------
def create_color_image(color_rgb: Tuple[int,int,int], width=240, height=140, seed=None) -> str:
    """
    Renders a rectangular color swatch with slight noise, returns PNG data URI.
    color_rgb: (r,g,b)
    """
    rnd = random.Random(seed)
    img = Image.new("RGB", (width, height), color_rgb)
    draw = ImageDraw.Draw(img)

    # add tiny semitransparent overlay noise
    for _ in range(int(width * height * 0.002)):
        x = rnd.randint(0, width-1)
        y = rnd.randint(0, height-1)
        dot = (min(255, color_rgb[0] + rnd.randint(-8,8)),
               min(255, color_rgb[1] + rnd.randint(-8,8)),
               min(255, color_rgb[2] + rnd.randint(-8,8)))
        draw.point((x,y), fill=dot)

    # maybe add a thin border
    border_color = tuple(max(0, c-30) for c in color_rgb)
    draw.rectangle([0, 0, width-1, height-1], outline=border_color)

    return pil_to_data_uri(img)

def guess_common_color_name(color_rgb: Tuple[int,int,int]) -> str:
    """
    Returns the nearest color name in our small lookup, fallback to hex-like name.
    """
    best = None
    best_dist = None
    for k, name in _COMMON_COLOR_NAMES.items():
        dist = math.sqrt(sum((a-b)**2 for a,b in zip(k, color_rgb)))
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = name
    if best_dist is not None and best_dist < 100:
        return best
    # fallback: hex
    return "#{:02x}{:02x}{:02x}".format(*color_rgb)

# ---------------------------
# Audio renderer
# ---------------------------
def create_audio_from_text(text: str, lang="en") -> str:
    """
    Uses gTTS to produce an mp3 data URI. Note: network required for TTS backend.
    """
    if not text:
        text = "Please type the word shown."
    tts = gTTS(text=text, lang=lang)
    bio = io.BytesIO()
    tts.write_to_fp(bio)
    mp3_bytes = bio.getvalue()
    return mp3_bytes_to_data_uri(mp3_bytes)

# ---------------------------
# Pattern UI helper
# ---------------------------
def prepare_pattern_ui(shapes: List[str], seed=None) -> Dict[str, Any]:
    """
    shapes: array-like labels (e.g. ["▲","●","◆","★"])
    Return a UI payload describing shapes and helpful hint text.
    The authoritative 'sequence' solution should be included by the AI model when creating the challenge.
    """
    rnd = random.Random(seed)
    # ensure uniqueness and shuffle for client variety
    uniq = []
    for s in shapes:
        if s not in uniq:
            uniq.append(s)
    # if too few shapes, expand with letters
    if len(uniq) < 4:
        base = [chr(ord('A') + i) for i in range(8)]
        for b in base:
            if b not in uniq:
                uniq.append(b)
            if len(uniq) >= 8:
                break
    # present a short hint
    hint = "Click the shapes in the order requested. Tap each shape once."
    return {"shapes": uniq, "hint": hint}

# ---------------------------
# Module quick self-test (when run directly)
# ---------------------------
if __name__ == "__main__":
    # Generate simple artifacts to visually inspect
    print("Generating sample color image...")
    data_uri = create_color_image((255, 165, 0), seed=42)
    print(data_uri[:200], "...")

    print("Generating sample text-image...")
    data_uri2 = create_image_from_description("Render the word 'hello' in quotes with noise", seed=123)
    print(data_uri2[:200], "...")
