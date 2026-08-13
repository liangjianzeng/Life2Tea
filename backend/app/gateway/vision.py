"""
vision.py — Vision support for the Unified Model Gateway.

Adds a small vision-language model (Qwen3.5-4B + mmproj) as a first-class
channel:

1. `POST /v1/vision/analyze` — direct "look at an image" tool for external
   agents; returns structured `{ocr, caption, objects, answer}`.
2. Automatic chat fallback — image-bearing messages are auto-described so a
   text-only main model (vv4flash) never crashes on image tokens.

The "describe-then-reason" pattern keeps the main model pure-text: images are
converted to structured text by the vision model before reaching the LLM.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .providers.base import EndpointStatus, GatewayError, Provider

vision_router = APIRouter(tags=["Vision"])

DEFAULT_DESCRIBE_PROMPT = (
    "请详细描述这张图片并输出结构化内容：画面内容、主要物体及其大致位置、"
    "全部文字(OCR，按布局排列)、图表/数据要点、以及整体理解。"
    "你的输出将交给一个大型语言模型继续处理任务，请尽量客观、完整、有条理。用中文输出。"
)

STRUCTURED_PROMPT = (
    "请以 JSON 格式回答（不要输出任何其他文字），包含四个字段："
    '"ocr"(图中所有文字), "caption"(一句话画面描述), '
    '"objects"(主要物体列表, JSON 数组), "answer"(对图片的综合理解)。'
)

PLACEHOLDER_NO_VISION = "【图片无法解析：无视觉模型可用】"
PLACEHOLDER_FAILED = "【图片无法解析：视觉模型未就绪】"


# ── Detection helpers ─────────────────────────────────────
def _has_images(messages: List[Dict[str, Any]]) -> bool:
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def find_vision_endpoint(manager):
    """Pick the vision endpoint: vision routing rule first, then any mmproj endpoint."""
    rules = {}
    try:
        rules = manager.get_routing() or {}
    except Exception:
        pass
    for name in rules.get("vision", []):
        endpoint = manager.get_endpoint(name)
        if endpoint is not None:
            return endpoint
    for endpoint in manager.list_endpoints():
        params = getattr(endpoint.spec, "params", {}) or {}
        if params.get("mmproj") or "mmproj" in endpoint.name.lower():
            return endpoint
    return None


def _vision_model_name(manager) -> str:
    endpoint = find_vision_endpoint(manager)
    return endpoint.name if endpoint is not None else ""


# ── Vision inference ──────────────────────────────────────
async def describe_image(manager, image_url: str, prompt: Optional[str] = None) -> str:
    """Send one image to the vision model and return its text answer."""
    endpoint = find_vision_endpoint(manager)
    if endpoint is None:
        raise GatewayError("No vision endpoint configured", 503, "vision_unavailable")
    if endpoint.status != EndpointStatus.RUNNING:
        try:
            endpoint = await manager.start(endpoint.name)
        except Exception as e:
            raise GatewayError(str(e), 503, "vision_start_failed")
    prompt = prompt or DEFAULT_DESCRIBE_PROMPT
    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": image_url}},
            {"type": "text", "text": prompt},
        ],
    }]
    provider = Provider(endpoint)
    result = await provider.chat_completion(
        messages, stream=False, max_tokens=512, temperature=0.3
    )
    choices = result.get("choices") or []
    if not choices:
        raise GatewayError("Vision model returned empty response", 502, "vision_empty")
    return choices[0]["message"]["content"]


async def sanitize_messages(manager, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Replace image parts with text descriptions so a text-only model can proceed.

    Never raises: on any failure it substitutes a placeholder so the chat turn
    survives instead of crashing the agent.
    """
    vision = find_vision_endpoint(manager)
    out: List[Dict[str, Any]] = []
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, str):
            out.append(msg)
            continue
        if not isinstance(content, list):
            out.append(msg)
            continue
        text_parts = [
            p["text"]
            for p in content
            if isinstance(p, dict) and p.get("type") == "text" and p.get("text")
        ]
        image_parts = [
            p for p in content if isinstance(p, dict) and p.get("type") == "image_url"
        ]
        joined = "\n".join(text_parts)
        if not image_parts:
            if joined:
                m = dict(msg)
                m["content"] = joined
                out.append(m)
            continue
        # images present → describe each
        new_text = joined
        for part in image_parts:
            url = part.get("image_url")
            url = url.get("url") if isinstance(url, dict) else url
            if not url:
                continue
            if vision is None:
                new_text += "\n" + PLACEHOLDER_NO_VISION + "\n"
                continue
            try:
                desc = await describe_image(manager, url, None)
                new_text += f"\n[图片描述] {desc}\n"
            except Exception:
                new_text += "\n" + PLACEHOLDER_FAILED + "\n"
        if new_text:
            m = dict(msg)
            m["content"] = new_text
            out.append(m)
    return out


async def prepare_chat(gateway, messages, model_pref):
    """Describe-then-reason for chat requests.

    Replaces image parts with vision-model text descriptions, then routes the
    sanitized (pure-text) messages to the main (large) model. The small vision
    model NEVER executes the agent task — it only supplies visual understanding
    as text, so the large model can continue the job.
    """
    sanitized_messages = await sanitize_messages(gateway.manager, messages)
    chain = gateway.router.route_chain(sanitized_messages, model_pref)
    return chain, sanitized_messages


# ── /v1/vision/analyze ────────────────────────────────────
class VisionAnalyzeRequest(BaseModel):
    image: str  # http(s) URL or base64 data URL
    prompt: Optional[str] = None
    structured: Optional[bool] = True


@vision_router.post("/v1/vision/analyze")
async def vision_analyze(req: VisionAnalyzeRequest, request: Request):
    """Analyze an image with the vision model → {ocr, caption, objects, answer}."""
    gateway = getattr(request.app.state, "gateway", None)
    if gateway is None:
        from .router_api import get_gateway

        gateway = get_gateway()
    manager = gateway.manager
    try:
        if req.structured:
            text = await describe_image(manager, req.image, STRUCTURED_PROMPT)
            parsed = _parse_structured(text)
            parsed.setdefault("answer", text)
            parsed["raw"] = text
            parsed["model"] = _vision_model_name(manager)
            return JSONResponse(content=parsed)
        text = await describe_image(manager, req.image, req.prompt)
        return JSONResponse(
            content={"answer": text, "raw": text, "model": _vision_model_name(manager)}
        )
    except GatewayError as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"error": {"message": e.message, "type": e.error_type}},
        )


def _parse_structured(text: str) -> Dict[str, Any]:
    """Best-effort JSON parse of the model's structured output."""
    try:
        t = text.strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1]
            if t.endswith("```"):
                t = t[:-3]
        data = json.loads(t)
        if isinstance(data, dict):
            return {
                k: data.get(k, "")
                for k in ("ocr", "caption", "objects", "answer")
            }
    except Exception:
        pass
    return {"answer": text}
