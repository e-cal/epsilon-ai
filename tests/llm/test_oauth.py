from __future__ import annotations

from dataclasses import replace

import pytest

from epsilon.llm.oauth import (
    OAuthApiKeyResult,
    OAuthAuthInfo,
    OAuthCredentials,
    OAuthProviderInterface,
    extract_openai_codex_account_id,
    get_oauth_api_key,
    get_oauth_provider,
    login_openai_codex,
    openai_codex_oauth_provider,
    parse_openai_codex_authorization_input,
    register_oauth_provider,
    reset_oauth_providers,
    unregister_oauth_provider,
)


def _jwt(payload: str) -> str:
    return f"header.{payload}.signature"


def _base64url(value: str) -> str:
    import base64

    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def test_openai_codex_oauth_provider_is_registered() -> None:
    provider = get_oauth_provider("codex")

    assert provider is not None
    assert provider.name == openai_codex_oauth_provider.name
    assert get_oauth_provider("openai-codex") is provider


def test_parse_openai_codex_authorization_input_accepts_urls_and_manual_values() -> None:
    assert parse_openai_codex_authorization_input("abc123") == ("abc123", None)
    assert parse_openai_codex_authorization_input("code=abc&state=xyz") == ("abc", "xyz")
    assert parse_openai_codex_authorization_input("https://example.test/cb?code=abc&state=xyz") == (
        "abc",
        "xyz",
    )


def test_extract_openai_codex_account_id_reads_jwt_claim() -> None:
    payload = _base64url('{"https://api.openai.com/auth":{"chatgpt_account_id":"acct_123"}}')

    assert extract_openai_codex_account_id(_jwt(payload)) == "acct_123"


@pytest.mark.asyncio
async def test_get_oauth_api_key_refreshes_expired_credentials() -> None:
    reset_oauth_providers()

    async def login(_callbacks):
        raise AssertionError("login should not be called")

    async def refresh_token(credentials: OAuthCredentials) -> OAuthCredentials:
        return replace(credentials, access="fresh-token", expires=credentials.expires + 10_000)

    provider = OAuthProviderInterface(
        id="test-oauth",
        name="Test OAuth",
        login=login,
        refresh_token=refresh_token,
        get_api_key=lambda credentials: credentials.access,
    )
    register_oauth_provider(provider)
    try:
        result = await get_oauth_api_key(
            "test-oauth",
            {"test-oauth": OAuthCredentials(access="stale", refresh="refresh", expires=0)},
        )
    finally:
        unregister_oauth_provider("test-oauth")
        reset_oauth_providers()

    assert isinstance(result, OAuthApiKeyResult)
    assert result.api_key == "fresh-token"
    assert result.new_credentials.access == "fresh-token"


@pytest.mark.asyncio
async def test_login_openai_codex_uses_browser_callback_when_available(monkeypatch) -> None:
    class FakeServer:
        async def wait_for_code(self) -> str | None:
            return "browser-code"

        def cancel_wait(self) -> None:
            return None

        async def close(self) -> None:
            return None

    payload = _base64url('{"https://api.openai.com/auth":{"chatgpt_account_id":"acct_browser"}}')
    seen_auth: list[OAuthAuthInfo] = []

    async def fake_flow(originator: str):
        assert originator == "epsilon"
        return "verifier", "state-1", "https://auth.test/login"

    async def fake_start_server(state: str):
        assert state == "state-1"
        return FakeServer()

    async def fake_exchange(code: str, verifier: str, *, redirect_uri: str = ""):
        assert code == "browser-code"
        assert verifier == "verifier"
        return type("Token", (), {"access": _jwt(payload), "refresh": "refresh", "expires": 123})()

    monkeypatch.setattr("epsilon.llm.oauth._create_openai_codex_authorization_flow", fake_flow)
    monkeypatch.setattr("epsilon.llm.oauth._start_openai_codex_oauth_server", fake_start_server)
    monkeypatch.setattr(
        "epsilon.llm.oauth._exchange_openai_codex_authorization_code",
        fake_exchange,
    )

    async def fail_prompt(prompt) -> str:
        pytest.fail(f"unexpected prompt: {prompt.message}")

    credentials = await login_openai_codex(
        on_auth=seen_auth.append,
        on_prompt=fail_prompt,
    )

    assert credentials.refresh == "refresh"
    assert credentials.account_id == "acct_browser"
    assert seen_auth == [
        OAuthAuthInfo(
            url="https://auth.test/login",
            instructions="A browser window should open. Complete login to finish.",
        )
    ]


@pytest.mark.asyncio
async def test_login_openai_codex_falls_back_to_manual_prompt(monkeypatch) -> None:
    class FakeServer:
        async def wait_for_code(self) -> str | None:
            return None

        def cancel_wait(self) -> None:
            return None

        async def close(self) -> None:
            return None

    payload = _base64url('{"https://api.openai.com/auth":{"chatgpt_account_id":"acct_manual"}}')

    async def fake_flow(originator: str):
        assert originator == "epsilon"
        return "verifier", "state-2", "https://auth.test/login"

    async def fake_start_server(state: str):
        assert state == "state-2"
        return FakeServer()

    async def fake_exchange(code: str, verifier: str, *, redirect_uri: str = ""):
        assert code == "manual-code"
        assert verifier == "verifier"
        return type("Token", (), {"access": _jwt(payload), "refresh": "refresh", "expires": 456})()

    monkeypatch.setattr("epsilon.llm.oauth._create_openai_codex_authorization_flow", fake_flow)
    monkeypatch.setattr("epsilon.llm.oauth._start_openai_codex_oauth_server", fake_start_server)
    monkeypatch.setattr(
        "epsilon.llm.oauth._exchange_openai_codex_authorization_code",
        fake_exchange,
    )

    credentials = await login_openai_codex(
        on_auth=lambda info: None,
        on_prompt=lambda prompt: _return("manual-code#state-2"),
    )

    assert credentials.access == _jwt(payload)
    assert credentials.account_id == "acct_manual"


async def _return(value: str) -> str:
    return value
