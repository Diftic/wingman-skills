"""
scanner.py — Screen capture and r_displayinfo extraction for SC NavPoint
Author: Mallachi

Learning points from SC_Signature_Scanner and old SC_MiningAssistant:
- Crop to the overlay region before OCR to reduce noise and improve accuracy
- Send BOTH full screenshot (context) AND cropped region (clarity) in one LLM call
  The two-image approach solved GPT-4o-mini inconsistency on tiny overlay text
- r_displayinfo appears in the top-right portion of the screen
- Upscale small crops before sending to improve text legibility
"""

import base64
import io
import json
import logging
import re

from PIL import Image
from mss import mss


logger = logging.getLogger(__name__)

# r_displayinfo is typically in the top-right portion of the screen
# Crop: right 45% width, top 55% height — captures the full overlay at any display size
_CROP_RIGHT_FRACTION = 0.45
_CROP_TOP_FRACTION = 0.55

# Full screenshot width for context image
_CONTEXT_WIDTH = 1200

# Cropped region width for detail image — higher res than context
_DETAIL_WIDTH = 900

_EXTRACTION_PROMPT = """You are analyzing Star Citizen debug overlay text (r_displayinfo 4).

I am providing TWO images:
  1. Full screenshot at reduced resolution — for visual context
  2. Cropped top-right region at higher resolution — this is where r_displayinfo appears

Focus on image 2. Find the r_displayinfo debug overlay — it is small white/grey monospace
text typically in the upper-right area showing system performance and position data.

Extract these exact values:

• x, y, z — player coordinates (very large floats, e.g. 12345678.23). The position line
  may appear as "Pos: x, y, z" or "x=... y=... z=..." or similar format.
• heading — player heading in degrees (0–360), if visible
• zone — current zone or entity name (e.g. "Hurston", "Area18", "MT DataCenter", "space")
• planet — parent planet if identifiable (e.g. "Hurston", "microTech", "Crusader", "ArcCorp")
• moon — moon name if on/near a moon (e.g. "Daymar", "Cellin", "Aberdeen")
• system — star system (e.g. "Stanton", "Pyro", "Nyx")
• server_id — any server identifier string visible in the overlay

Return ONLY a JSON object with these keys. Use null for any value not visible.
If r_displayinfo is not enabled, return {"error": "r_displayinfo not visible"}.

Example: {"x": 12345678.23, "y": -98765432.11, "z": 456789.45, "heading": 127.5,
          "zone": "Area18", "planet": "ArcCorp", "moon": null,
          "system": "Stanton", "server_id": "live-us-east-1.123456"}"""


class NavPointScanner:
    """Captures the screen and provides message data for position extraction via Vision AI."""

    def __init__(self) -> None:
        pass

    def capture_screen_b64(self, display: int = 1) -> tuple[str, str]:
        """Capture the current screen and return two base64-encoded PNG images.

        Returns:
            (context_b64, detail_b64) — full screenshot + cropped top-right region.
        """
        with mss() as sct:
            monitors = sct.monitors
            # monitors[0] = combined virtual desktop; monitors[1+] = physical displays
            idx = min(display, len(monitors) - 1)
            mon = monitors[idx]
            screenshot = sct.grab(mon)
            image = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # --- Context image: full screenshot at reduced width ---
        ctx_h = int(_CONTEXT_WIDTH * image.height / image.width)
        context_img = image.resize((_CONTEXT_WIDTH, ctx_h), Image.LANCZOS)
        context_b64 = self._to_b64(context_img)

        # --- Detail image: top-right crop at higher resolution ---
        w, h = image.size
        crop_x = int(w * (1 - _CROP_RIGHT_FRACTION))
        crop_y = 0
        crop_w = w - crop_x
        crop_h = int(h * _CROP_TOP_FRACTION)
        cropped = image.crop((crop_x, crop_y, w, crop_h))

        # Upscale if the crop is small (improves OCR on small text, per SC_Signature_Scanner)
        if cropped.width < _DETAIL_WIDTH:
            scale = _DETAIL_WIDTH / cropped.width
            cropped = cropped.resize(
                (int(cropped.width * scale), int(cropped.height * scale)),
                Image.LANCZOS,
            )
        else:
            # Resize to detail width to avoid oversized payloads
            d_h = int(_DETAIL_WIDTH * cropped.height / cropped.width)
            cropped = cropped.resize((_DETAIL_WIDTH, d_h), Image.LANCZOS)

        detail_b64 = self._to_b64(cropped)
        return context_b64, detail_b64

    @staticmethod
    def _to_b64(img: Image.Image) -> str:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def build_extraction_messages(self, context_b64: str, detail_b64: str) -> list[dict]:
        """Build the LLM message list for position extraction using two images."""
        return [
            {
                "role": "system",
                "content": (
                    "You are a precise data extraction assistant. "
                    "Extract only values explicitly visible in the images. "
                    "Return valid JSON only, no other text."
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _EXTRACTION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{context_b64}",
                            "detail": "low",
                        },
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{detail_b64}",
                            "detail": "high",
                        },
                    },
                ],
            },
        ]

    def parse_completion(self, completion) -> dict | None:
        """Parse the LLM completion into a position data dict."""
        if not completion or not completion.choices:
            return None
        raw = completion.choices[0].message.content or ""
        return self._parse_json_response(raw)

    def _parse_json_response(self, raw: str) -> dict | None:
        """Strip markdown fences and parse JSON."""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning("Could not parse LLM response as JSON: %.200s", raw)
            return None

        if "error" in data:
            logger.info("LLM extraction error: %s", data["error"])
            return None

        result: dict = {}

        # Numeric fields
        for key in ("x", "y", "z", "heading"):
            val = data.get(key)
            if val is not None:
                try:
                    result[key] = float(val)
                except (TypeError, ValueError):
                    pass

        # Require at least x, y, z
        if not all(k in result for k in ("x", "y", "z")):
            logger.info("Extraction incomplete — missing x/y/z coordinates")
            return None

        # String fields
        for key in ("zone", "planet", "moon", "system", "server_id"):
            val = data.get(key)
            result[key] = str(val) if val and str(val).lower() not in ("null", "none") else ""

        return result
