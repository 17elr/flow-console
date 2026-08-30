from __future__ import annotations

import base64
import os
import uuid
import time
from threading import Lock
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import httpx

_health_cache: dict[str, tuple[float, Dict[str, Any]]] = {}
_health_cache_lock = Lock()


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key_env: str


@dataclass(frozen=True)
class ImageInput:
    filename: str
    content: bytes
    mime_type: str = "image/png"


class ProviderError(RuntimeError):
    pass


class ProviderTransientError(ProviderError):
    pass


class ProviderPermanentError(ProviderError):
    pass


class ImageProvider:
    def __init__(self, config: ProviderConfig):
        self.config = config

    def health_check(self) -> Dict[str, Any]:
        return {
            "provider": self.config.provider,
            "model": self.config.model,
            "configured": bool(os.getenv(self.config.api_key_env)),
            "network_call": False,
        }

    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def edit(self, reference_images: Iterable[ImageInput], prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    def get_capabilities(self) -> Dict[str, Any]:
        return {"generate": True, "edit": True, "output_format": "png", "network_enabled": bool(os.getenv(self.config.api_key_env))}

    def remote_health_check(self) -> Dict[str, Any]:
        cache_key = f"{self.config.provider}:{self.config.model}"
        with _health_cache_lock:
            cached = _health_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < 300:
                return cached[1]
        request_id = f"commerce-provider-check-{uuid.uuid4().hex}"
        try:
            with httpx.Client(timeout=20, follow_redirects=True) as client:
                response = client.get(f"{self.config.base_url.rstrip('/')}/models", headers=self._headers(request_id))
                self._raise_for_status(response)
                models = [str(item.get("id", "")) for item in (response.json().get("data") or []) if isinstance(item, dict)]
            result = {"available": self.config.model in models, "model_visible": self.config.model in models, "model_count": len(models), "error": None}
        except ProviderError as exc:
            result = {"available": False, "model_visible": False, "model_count": 0, "error": str(exc)}
        except (httpx.HTTPError, ValueError) as exc:
            result = {"available": False, "model_visible": False, "model_count": 0, "error": type(exc).__name__}
        with _health_cache_lock:
            _health_cache[cache_key] = (time.monotonic(), result)
        return result

    def _headers(self, request_id: str) -> dict[str, str]:
        key = os.getenv(self.config.api_key_env)
        if not key:
            raise ProviderPermanentError(f"{self.config.api_key_env} is not configured")
        return {"Authorization": f"Bearer {key}", "X-Request-ID": request_id}

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = ""
        try:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            detail = str(error.get("message", "")) if isinstance(error, dict) else ""
        except ValueError:
            pass
        message = f"{self.config.provider} request failed ({response.status_code})"
        if detail:
            message = f"{message}: {detail[:240]}"
        if response.status_code == 429 or response.status_code >= 500:
            raise ProviderTransientError(message)
        raise ProviderPermanentError(message)

    def normalize_response(self, payload: Dict[str, Any], request_id: str, client: httpx.Client) -> Dict[str, Any]:
        images: list[bytes] = []
        for item in payload.get("data") or []:
            if item.get("b64_json"):
                images.append(base64.b64decode(item["b64_json"]))
            elif item.get("url"):
                response = client.get(item["url"], timeout=60)
                self._raise_for_status(response)
                images.append(response.content)
        if not images:
            raise ProviderPermanentError("Image response contained no image data")
        return {
            "images": images,
            "request_id": request_id,
            "provider": self.config.provider,
            "model": self.config.model,
            "usage": payload.get("usage"),
            "metadata": {key: value for key, value in payload.items() if key not in {"data"}},
        }


class HensunImageProvider(ImageProvider):
    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_id = f"commerce-hensun-{uuid.uuid4().hex}"
        payload = {"model": self.config.model, "prompt": prompt, "n": int((options or {}).get("n", 1))}
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.post(f"{self.config.base_url.rstrip('/')}/images/generations", headers=self._headers(request_id), json=payload)
            self._raise_for_status(response)
            return self.normalize_response(response.json(), response.headers.get("x-request-id", request_id), client)

    def edit(self, reference_images: Iterable[ImageInput], prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_id = f"commerce-hensun-edit-{uuid.uuid4().hex}"
        files = [("image", (item.filename, item.content, item.mime_type)) for item in reference_images]
        if not files:
            raise ProviderPermanentError("At least one reference image is required")
        data = {"model": self.config.model, "prompt": prompt, "n": str(int((options or {}).get("n", 1)))}
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.post(f"{self.config.base_url.rstrip('/')}/images/edits", headers=self._headers(request_id), files=files, data=data)
            self._raise_for_status(response)
            return self.normalize_response(response.json(), response.headers.get("x-request-id", request_id), client)


class OpenAIImageProvider(ImageProvider):
    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_id = f"commerce-openai-{uuid.uuid4().hex}"
        opts = options or {}
        payload: dict[str, Any] = {"model": self.config.model, "prompt": prompt, "n": int(opts.get("n", 1)), "output_format": "png"}
        for key in ("size", "quality"):
            if opts.get(key):
                payload[key] = opts[key]
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.post(f"{self.config.base_url.rstrip('/')}/images/generations", headers=self._headers(request_id), json=payload)
            self._raise_for_status(response)
            return self.normalize_response(response.json(), response.headers.get("x-request-id", request_id), client)

    def edit(self, reference_images: Iterable[ImageInput], prompt: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request_id = f"commerce-openai-edit-{uuid.uuid4().hex}"
        opts = options or {}
        files = [("image", (item.filename, item.content, item.mime_type)) for item in reference_images]
        data: dict[str, str] = {"model": self.config.model, "prompt": prompt, "n": str(int(opts.get("n", 1))), "output_format": "png"}
        for key in ("size", "quality"):
            if opts.get(key):
                data[key] = str(opts[key])
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            response = client.post(f"{self.config.base_url.rstrip('/')}/images/edits", headers=self._headers(request_id), files=files, data=data)
            self._raise_for_status(response)
            return self.normalize_response(response.json(), response.headers.get("x-request-id", request_id), client)


def configured_provider() -> ImageProvider:
    provider = os.getenv("IMAGE_PROVIDER", "hensun").lower()
    if provider == "openai":
        return OpenAIImageProvider(ProviderConfig("openai", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"), os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"), "OPENAI_API_KEY"))
    return HensunImageProvider(ProviderConfig("hensun", os.getenv("HENSUN_BASE_URL", "https://hensunai.com/v1"), os.getenv("HENSUN_MODEL", "gpt-image-2"), "HENSUN_API_KEY"))
