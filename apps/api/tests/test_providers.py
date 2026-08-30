from __future__ import annotations

import pytest

from app.providers import HensunImageProvider, ImageInput, ProviderConfig, ProviderPermanentError


def test_provider_requires_credentials_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HENSUN_API_KEY", raising=False)
    provider = HensunImageProvider(
        ProviderConfig(
            provider="hensun",
            base_url="https://hensunai.com/v1",
            model="gpt-image-2",
            api_key_env="HENSUN_API_KEY",
        )
    )

    assert provider.health_check() == {
        "provider": "hensun",
        "model": "gpt-image-2",
        "configured": False,
        "network_call": False,
    }
    assert provider.get_capabilities()["network_enabled"] is False
    with pytest.raises(ProviderPermanentError, match="not configured"):
        provider.generate("must not run")
    with pytest.raises(ProviderPermanentError, match="not configured"):
        provider.edit([ImageInput("reference.png", b"png")], "must not run")


def test_local_frontend_origins_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API_CORS_ORIGINS", raising=False)
    from app.main import origins

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins
