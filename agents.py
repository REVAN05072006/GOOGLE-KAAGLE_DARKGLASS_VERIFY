# agents.py
import json
import time
from gemini_client import decide_and_create_challenge, verify_with_ai
from captcha_generator import (
    create_image_from_description,
    create_audio_from_text,
    create_color_image,
    prepare_pattern_ui
)
from security import sign_payload, verify_signature
from sessions import session_store

class GeneratorAgent:
    def run(self, session_id):
        session = session_store.get(session_id)
        if not session:
            return {"error": "invalid-session"}

        # 1) Ask AI or fallback generator to produce a challenge
        challenge = decide_and_create_challenge(session_id)

        ctype = challenge.get("captcha_type")
        ui_data = challenge.get("ui_data", {}) or {}
        rendered_ui = dict(ui_data)  # copy for storing+returning

        try:
            # -------------------
            # IMAGE CAPTCHA
            # -------------------
            if ctype == "image":
                desc = ui_data.get("description", "")
                seed = hash(challenge.get("captcha_id"))
                rendered_ui["image_base64"] = create_image_from_description(desc, seed=seed)

            # -------------------
            # AUDIO CAPTCHA
            # -------------------
            elif ctype == "audio":
                text = ui_data.get("text", "")
                rendered_ui["audio_base64"] = create_audio_from_text(text)

            # -------------------
            # PATTERN CAPTCHA
            # -------------------
            elif ctype == "pattern":
                shapes = ui_data.get("shapes", [])
                seed = hash(challenge.get("captcha_id"))
                rendered_ui = prepare_pattern_ui(shapes, seed=seed)

            # -------------------
            # COLOR CAPTCHA
            # -------------------
            elif ctype == "color":
                rgb = ui_data.get("color_rgb")
                if isinstance(rgb, list) and len(rgb) == 3:
                    seed = hash(challenge.get("captcha_id"))
                    rendered_ui["image_base64"] = create_color_image(tuple(rgb), seed=seed)
                else:
                    raise Exception("Invalid color_rgb")

            # -------------------
            # TEXT / MATH CAPTCHA
            # -------------------
            elif ctype in ("text", "math"):
                # nothing to render; UI question is textual
                pass

            # -------------------
            # UNKNOWN / UNSUPPORTED CAPTCHA TYPE
            # -------------------
            else:
                raise Exception(f"Unsupported captcha_type '{ctype}'")

        except Exception as e:
            # If ANY rendering fails → fallback simple text CAPTCHA
            fallback_word = "solara" + str(int(time.time()) % 10000)
            challenge = {
                "captcha_id": challenge.get("captcha_id", "fallback-" + str(int(time.time()))),
                "captcha_type": "text",
                "instructions": f"Type the word '{fallback_word}'",
                "ui_data": {"question": f"Type the word '{fallback_word}'"},
                "solution": {"value": fallback_word},
                "metadata": {"fallback": True, "render_error": str(e)}
            }
            rendered_ui = challenge["ui_data"]

        # 2) Save challenge + signature in session store
        challenge_to_store = dict(challenge)
        challenge_to_store["ui_data"] = rendered_ui

        challenge_repr = json.dumps(challenge_to_store, sort_keys=True, ensure_ascii=False)
        signature = sign_payload(session_id, challenge_repr)

        session_store.update(session_id, {
            "captcha": {
                "challenge": challenge_to_store,
                "signature": signature,
                "created": time.time()
            },
            "attempts": 0,
            "last_attempt": 0,
            "generation_count": session.get("generation_count", 0) + 1
        })

        # 3) Return minimal challenge to client
        return {
            "captcha_id": challenge_to_store.get("captcha_id"),
            "captcha_type": challenge_to_store.get("captcha_type"),
            "instructions": challenge_to_store.get("instructions"),
            "ui_data": challenge_to_store.get("ui_data"),
            "signature": signature
        }


class ValidatorAgent:
    def run(self, session_id, user_answer):
        session = session_store.get(session_id)
        if not session or not session.get("captcha"):
            return {"success": False, "error": "No active captcha"}

        stored = session["captcha"]
        challenge = stored.get("challenge")
        signature = stored.get("signature")

        # 1) Verify signature integrity
        challenge_repr = json.dumps(challenge, sort_keys=True, ensure_ascii=False)
        if not verify_signature(session_id, challenge_repr, signature):
            return {"success": False, "error": "Stored challenge failed signature verification"}

        # 2) Rate limiting
        now = time.time()
        attempts = session.get("attempts", 0)
        last = session.get("last_attempt", 0)
        if attempts >= 6 and now - last < 60:
            return {"success": False, "error": "Too many attempts. Try again later."}

        # 3) AI verification or local fallback
        verify_result = verify_with_ai(challenge, user_answer)

        session_store.update(session_id, {
            "attempts": attempts + 1,
            "last_attempt": now
        })

        if not verify_result.get("ok"):
            return {
                "success": False,
                "error": "verification_unavailable",
                "meta": verify_result.get("explanation")
            }

        # 4) Interpret verification result
        correct = bool(verify_result.get("correct", False))
        explanation = verify_result.get("explanation", "")
        normalized = verify_result.get("normalized") or verify_result.get("normalized_answer")

        if correct:
            session_store.update(session_id, {"captcha": None, "attempts": 0})
            return {
                "success": True,
                "message": "Captcha correct",
                "explanation": explanation,
                "normalized": normalized
            }

        return {
            "success": False,
            "message": "Incorrect captcha",
            "explanation": explanation,
            "normalized": normalized
        }
