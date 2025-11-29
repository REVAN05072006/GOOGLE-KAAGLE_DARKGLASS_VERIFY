# gemini_client.py
"""
AI / fallback client for deciding and verifying CAPTCHAs.

Behavior:
 - If GEMINI_API_KEY and GEMINI_API_ENDPOINT are set, attempt to call the remote
   generative endpoint. The endpoint is expected to return a JSON object only.
 - If the remote call fails or isn't configured, use a strong local fallback
   generator that produces many captcha types:
     - image: ui_data.description (text describing text or shapes)
     - audio: ui_data.text (what to speak), solution.value
     - pattern: ui_data.shapes + solution.sequence
     - text: ui_data.question + solution.value
     - math: ui_data.question + solution.value
     - color: ui_data.color_rgb (r,g,b) and ui_data.hint; solution.value is a color-name or hex
 - verify_with_ai: attempts remote verification first; if unavailable, falls back
   to local heuristics for each captcha type.
"""
import os
import json
import uuid
import random
import requests
import math
from dotenv import load_dotenv
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_ENDPOINT = os.getenv("GEMINI_API_ENDPOINT")  # text endpoint that accepts {"prompt":...}
HEADERS = {"Content-Type": "application/json"}
if GEMINI_API_KEY:
    HEADERS["Authorization"] = f"Bearer {GEMINI_API_KEY}"

# Simple helpers for local generator
def _rand_id():
    return uuid.uuid4().hex[:12]

def _rand_word(rnd, max_len=6):
    # small dictionary-like random tokens mixing letters and digits
    syllables = ["sol", "ra", "pix", "tor", "len", "mar", "kai", "zen", "net", "mono", "tri", "qua"]
    w = []
    target = rnd.randint(3, max_len)
    while len("".join(w)) < target:
        w.append(rnd.choice(syllables))
    s = "".join(w)[:target]
    # sometimes add digits
    if rnd.random() < 0.25:
        s = s + str(rnd.randint(2, 99))
    return s

def _nearest_color_name(rgb):
    # small builtin mapping (keeps consistent with captcha_generator fallback naming)
    common = {
        "red": (255,0,0), "green": (0,255,0), "blue": (0,0,255),
        "yellow": (255,255,0), "orange": (255,165,0), "purple": (128,0,128),
        "pink": (255,192,203), "black": (0,0,0), "white": (255,255,255),
        "gray": (128,128,128), "brown": (165,42,42), "cyan": (0,255,255)
    }
    best = None; bestd = None
    for name, c in common.items():
        d = math.sqrt(sum((a-b)**2 for a,b in zip(c, rgb)))
        if bestd is None or d < bestd:
            bestd, best = d, name
    if bestd is not None and bestd < 150:
        return best
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def _local_generate_random_challenge(session_id: str, seed=None):
    rnd = random.Random(seed or uuid.uuid4().int)
    ctype = rnd.choice(["text","math","pattern","image","audio","color"])
    cid = _rand_id()
    out = {
        "captcha_id": cid,
        "captcha_type": ctype,
        "instructions": "",
        "ui_data": {},
        "solution": {}
    }

    if ctype == "text":
        word = _rand_word(rnd, max_len=6)
        out["instructions"] = f"Type the word shown (case-insensitive)."
        out["ui_data"] = {"question": f"Type the word '{word}'", "hint": "case-insensitive"}
        out["solution"] = {"value": word}
    elif ctype == "math":
        # generate small arithmetic or simple expression
        a = rnd.randint(2, 18)
        b = rnd.randint(1, 12)
        op = rnd.choice(["+", "-", "*"])
        if op == "+":
            val = a + b
        elif op == "-":
            val = a - b
        else:
            val = a * b
        out["instructions"] = "Solve the arithmetic expression and type the result."
        out["ui_data"] = {"question": f"What is {a} {op} {b} ?"}
        out["solution"] = {"value": str(val)}
    elif ctype == "pattern":
        # create 4-7 unique shapes or symbols and a random sequence
        pool = ["▲","●","◆","■","★","✦","⬟","⬢","◯","■","△"]
        rnd.shuffle(pool)
        count = rnd.randint(4, 7)
        shapes = pool[:count]
        seq_len = rnd.randint(3, min(6, count))
        seq = rnd.sample(list(range(count)), seq_len)  # indices
        # server solution uses 0-based indices; client may send array of indices
        out["instructions"] = "Click the shapes in the required order."
        out["ui_data"] = {"shapes": shapes}
        out["solution"] = {"sequence": seq}
    elif ctype == "image":
        # describe a noisy image with either a short word (which renderer will write)
        word = _rand_word(rnd, max_len=6)
        # maybe choose a click-based point challenge
        if rnd.random() < 0.45:
            # point challenge: instruct user to click near a symbol or ring
            x = rnd.randint(40, 380)
            y = rnd.randint(30, 170)
            tol = rnd.randint(12, 28)
            desc = f"Render a noisy background with the word '{word}' prominently. Also include a small subtle ring near coordinates approx {x},{y} (for a click-point target)."
            out["instructions"] = "Click the indicated target in the image."
            out["ui_data"] = {"description": desc, "hint": "Click the small ring or target in the image."}
            out["solution"] = {"x": x, "y": y, "tolerance": tol}
        else:
            # text-based image challenge: ask to type the word seen
            desc = f"Render a noisy image containing the word '{word}' with rotated letters and background random shapes."
            out["instructions"] = "Type the word shown in the image (case-insensitive)."
            out["ui_data"] = {"description": desc, "hint": "Type the word you can read"}
            out["solution"] = {"value": word}
    elif ctype == "audio":
        # produce a short spoken phrase (letters or words)
        if rnd.random() < 0.5:
            word = _rand_word(rnd, max_len=4)
            text = f"Please type the word {word}"
            out["instructions"] = "Listen to the audio and type what you hear."
            out["ui_data"] = {"text": text, "hint": "case-insensitive"}
            out["solution"] = {"value": word}
        else:
            # numeric sequence
            nums = [str(rnd.randint(2,9)) for _ in range(rnd.randint(2,4))]
            seq = " ".join(nums)
            text = f"Type the numbers: {seq}"
            out["instructions"] = "Listen and type the numbers spoken."
            out["ui_data"] = {"text": text, "hint": "digits separated by space"}
            out["solution"] = {"value": seq}
    elif ctype == "color":
        # choose a color and instruct the user to type its name
        palette = [
            (255,0,0),(0,255,0),(0,0,255),(255,255,0),(255,165,0),
            (128,0,128),(255,192,203),(0,0,0),(255,255,255),(128,128,128),(165,42,42)
        ]
        color = rnd.choice(palette)
        cname = _nearest_color_name(color)
        out["instructions"] = "Type the name (or hex) of the color shown."
        out["ui_data"] = {"color_rgb": list(color), "hint": "Common names or hex are accepted (case-insensitive)."}
        out["solution"] = {"value": cname}
    else:
        # fallback to text
        word = _rand_word(rnd)
        out["captcha_type"] = "text"
        out["instructions"] = f"Type the word '{word}'"
        out["ui_data"] = {"question": f"Type the word '{word}'"}
        out["solution"] = {"value": word}

    # attach generator metadata
    out["metadata"] = {"generated_by": "local_fallback", "seed": seed}
    return out

# -------------------------------------------------------------------------
# POST helper
# -------------------------------------------------------------------------
def _post_prompt(prompt: str, max_tokens=512, timeout=8):
    """
    Generic helper to POST to a text-based generative endpoint.
    Expects the endpoint to return raw text that contains a JSON object.
    """
    if not GEMINI_API_ENDPOINT or not GEMINI_API_KEY:
        raise RuntimeError("Gemini gen-lang not configured")
    payload = {"prompt": prompt, "max_output_tokens": max_tokens, "temperature": 0.7}
    r = requests.post(GEMINI_API_ENDPOINT, json=payload, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text

# -------------------------------------------------------------------------
# Decide & create challenge (primary function used by agents.py)
# Tries remote model first; falls back to local generator on any failure.
# -------------------------------------------------------------------------
def decide_and_create_challenge(session_id: str):
    """
    Returns a JSON-like dict describing the captcha:
    {
      "captcha_id": "<id>",
      "captcha_type": "image"|"audio"|"pattern"|"text"|"math"|"color",
      "instructions": "...",
      "ui_data": {...},
      "solution": {...}
    }
    """
    # If model endpoint configured, ask it to produce only JSON
    if GEMINI_API_ENDPOINT and GEMINI_API_KEY:
        prompt = (
            "You are a secure CAPTCHA generator. Output ONLY a SINGLE JSON object.\n"
            "Pick one captcha_type from [image, audio, pattern, text, math, color] and produce fields:\n"
            " - captcha_id: string\n"
            " - captcha_type: as above\n"
            " - instructions: short human-facing instruction\n"
            " - ui_data: object with rendering data. For image: provide 'description' text. For audio: 'text' to speak. For pattern: 'shapes' array. For color: 'color_rgb' [r,g,b]. For text/math: 'question'\n"
            " - solution: canonical solution object. For image click-target provide {\"x\":int,\"y\":int,\"tolerance\":int} OR for word-based provide {\"value\":\"...\"}. For pattern provide {\"sequence\":[indices]}. For color provide {\"value\":\"red\"} or hex.\n"
            "Make each captcha unpredictable, variable, and human-solvable. Do NOT include any explanatory prose or code fences. Return JSON ONLY."
        )
        try:
            raw = _post_prompt(prompt, max_tokens=900, timeout=8)
            # Try to extract JSON from raw response
            try:
                data = json.loads(raw)
            except Exception:
                s = raw.find("{")
                e = raw.rfind("}") + 1
                data = json.loads(raw[s:e])
            # validate minimally and fill missing bits
            if "captcha_id" not in data:
                data["captcha_id"] = _rand_id()
            if "captcha_type" not in data:
                data["captcha_type"] = "text"
            return data
        except Exception as e:
            # remote failed: fall through to local fallback
            # (we don't raise because fallback is robust)
            # optional: log e
            # print("Remote generate failed:", e)
            pass

    # Local fallback generation
    return _local_generate_random_challenge(session_id)

# -------------------------------------------------------------------------
# Ask the model to verify a stored challenge + user answer; model returns JSON:
# { "correct": true/false, "explanation":"...", "normalized_answer": "..." }
# If remote fails, fallback to heuristics below.
# -------------------------------------------------------------------------
def verify_with_ai(stored_challenge: dict, user_answer):
    # Attempt remote verification if configured
    if GEMINI_API_ENDPOINT and GEMINI_API_KEY:
        try:
            challenge_json = json.dumps(stored_challenge, ensure_ascii=False)
            user_json = json.dumps(user_answer, ensure_ascii=False)
            prompt = (
                "You are a secure CAPTCHA verification model. You will receive a JSON describing a CAPTCHA "
                "and a user's answer. Respond ONLY with a JSON object with fields:\n"
                "- correct: true or false\n"
                "- explanation: brief text\n"
                "- normalized_answer: canonical form of user's answer if relevant\n"
                "Do not output anything else.\n\nCHALLENGE:\n" + challenge_json + "\n\nUSER_ANSWER:\n" + user_json
            )
            raw = _post_prompt(prompt, max_tokens=400, timeout=6)
            try:
                data = json.loads(raw)
            except Exception:
                s = raw.find("{")
                e = raw.rfind("}") + 1
                data = json.loads(raw[s:e])
            return {"ok": True, "correct": bool(data.get("correct", False)), "explanation": data.get("explanation",""), "normalized": data.get("normalized_answer", None)}
        except Exception as e:
            # remote verification unavailable; fall back to local heuristics
            # (optional: log e)
            pass

    # Local verification heuristics
    try:
        ctype = stored_challenge.get("captcha_type")
        sol = stored_challenge.get("solution", {})
        # TEXT / MATH / AUDIO simple compare (case-insensitive)
        if ctype in ("text", "math", "audio"):
            expected = str(sol.get("value","")).strip().lower()
            provided = str(user_answer).strip().lower()
            return {"ok": True, "correct": expected == provided, "explanation":"fallback-exact-compare", "normalized_answer": provided}
        elif ctype == "pattern":
            expected_seq = sol.get("sequence") or sol.get("value")
            if isinstance(user_answer, str):
                # assume comma separated indices or labels
                if "," in user_answer:
                    arr = [int(x.strip()) for x in user_answer.split(",") if x.strip().isdigit()]
                    user_seq = arr
                else:
                    # maybe labels, not indices: attempt no-op (fail if not matching)
                    user_seq = user_answer
            elif isinstance(user_answer, list):
                user_seq = user_answer
            else:
                user_seq = []
            return {"ok": True, "correct": user_seq == expected_seq, "explanation":"fallback-sequence-compare", "normalized_answer": user_seq}
        elif ctype == "image":
            # If solution has a point, compare with tolerance
            if "x" in sol and "y" in sol:
                try:
                    tx = int(sol.get("x"))
                    ty = int(sol.get("y"))
                    tol = int(sol.get("tolerance", 18))
                    if isinstance(user_answer, dict):
                        ux = int(user_answer.get("x", -9999))
                        uy = int(user_answer.get("y", -9999))
                    elif isinstance(user_answer, (list, tuple)) and len(user_answer) >= 2:
                        ux, uy = int(user_answer[0]), int(user_answer[1])
                    else:
                        return {"ok": True, "correct": False, "explanation":"fallback-bad-input-for-image"}
                    dist = math.hypot(ux - tx, uy - ty)
                    return {"ok": True, "correct": dist <= tol, "explanation":"fallback-point", "normalized_answer": {"distance": dist}}
                except Exception as ex:
                    return {"ok": False, "correct": False, "explanation":"fallback-exception-image", "error": str(ex)}
            else:
                # word-based image
                expected = str(sol.get("value","")).strip().lower()
                provided = str(user_answer).strip().lower()
                return {"ok": True, "correct": expected == provided, "explanation":"fallback-image-word-compare", "normalized_answer": provided}
        elif ctype == "color":
            expected = str(sol.get("value","")).strip().lower()
            provided = str(user_answer).strip().lower()
            # allow small normalization: hex to lower, color names lower
            # If expected is hex like #rrggbb, accept either name or hex
            return {"ok": True, "correct": expected == provided, "explanation":"fallback-color-compare", "normalized_answer": provided}
        else:
            return {"ok": False, "correct": False, "explanation":"unsupported-type-fallback"}
    except Exception as ex:
        return {"ok": False, "correct": False, "explanation":"fallback-exception", "error": str(ex)}
