# Copyright (c) 2024 HephaestusForge. All Rights Reserved.
"""Creative Brief helpers for Mission Control."""

from __future__ import annotations

import base64
from typing import Any


BRIEF_SLOT_NAMES = ("cast", "style", "shot")


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[: max_len - 3].rstrip() + "..."
    return text


def _empty_slots(source: str = "reference_image") -> dict[str, dict[str, str]]:
    return {
        name: {"state": "pending", "value": "", "source": source}
        for name in BRIEF_SLOT_NAMES
    }


def _attachment_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    image_url = _clean_text(payload.get("image_url"), max_len=4096)
    image_bytes_b64 = _clean_text(payload.get("image_bytes_b64"), max_len=20_000_000)
    if not image_url and not image_bytes_b64:
        return None

    source = "url" if image_url and not image_url.startswith("data:") else "upload"
    name = _clean_text(payload.get("image_name")) or ("reference image" if source == "upload" else image_url)
    image_type = _clean_text(payload.get("image_type"), max_len=128)
    size = None
    if image_bytes_b64:
        try:
            size = len(base64.b64decode(image_bytes_b64, validate=True))
        except Exception:
            size = None

    return {
        "name": name,
        "type": image_type,
        "source": source,
        "size": size,
        "url": image_url,
    }


def build_reference_image_brief_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a UI-safe Creative Brief update from a reference image payload.

    This intentionally does not infer cast/style/shot from filename, bytes, or
    raw captions. Slots become constrained only from explicit constraint fields,
    leaving vision caption ingress to supply those fields later.
    """

    attachment = _attachment_from_payload(payload)
    if not attachment:
        return {
            "ok": False,
            "status": "error",
            "message": "Attach an image upload or image URL before updating the Creative Brief.",
            "slots": {},
        }

    caption = _clean_text(payload.get("caption"), max_len=2000)
    constraints = payload.get("constraints")
    if not isinstance(constraints, dict):
        constraints = {}

    slots = _empty_slots(source="vision_caption" if caption else "reference_image")
    applied = False
    for name in BRIEF_SLOT_NAMES:
        value = _clean_text(constraints.get(name))
        if value:
            slots[name] = {"state": "constrained", "value": value, "source": "manual"}
            applied = True

    if applied:
        status = "manual_constraints_applied"
        message = "Reference image attached. Manual Creative Brief constraints are applied."
    elif caption:
        status = "caption_received"
        message = "Reference image caption received. Add cast, style, and shot constraints before creating."
    else:
        status = "awaiting_vision_caption"
        message = (
            "Reference image attached; awaiting vision caption ingress. "
            "Add manual cast, style, and shot constraints meanwhile."
        )

    return {
        "ok": True,
        "status": status,
        "message": message,
        "attachment": attachment,
        "caption": caption,
        "slots": slots,
    }
