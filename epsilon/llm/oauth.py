from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import platform
import secrets
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

import httpx

if TYPE_CHECKING:
    from .types import Model

CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
TOKEN_URL = "https://auth.openai.com/oauth/token"
REDIRECT_URI = "http://localhost:1455/auth/callback"
SCOPE = "openid profile email offline_access"
OPENAI_AUTH_CLAIM_PATH = "https://api.openai.com/auth"
OPENAI_CODEX_PROVIDER_ID = "openai-codex"
DEFAULT_OPENAI_CODEX_ORIGINATOR = "epsilon"


type OAuthProviderId = str


@dataclass(slots=True)
class OAuthCredentials:
    refresh: str
    access: str
    expires: int
    account_id: str | None = None
    extra: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OAuthPrompt:
    message: str
    placeholder: str | None = None
    allow_empty: bool = False


@dataclass(slots=True)
class OAuthAuthInfo:
    url: str
    instructions: str | None = None


@dataclass(slots=True)
class OAuthLoginCallbacks:
    on_auth: Callable[[OAuthAuthInfo], None]
    on_prompt: Callable[[OAuthPrompt], Awaitable[str]]
    on_progress: Callable[[str], None] | None = None
    on_manual_code_input: Callable[[], Awaitable[str]] | None = None
    signal: object | None = None


@dataclass(slots=True)
class OAuthProviderInfo:
    id: OAuthProviderId
    name: str
    available: bool = True


@dataclass(slots=True)
class OAuthApiKeyResult:
    new_credentials: OAuthCredentials
    api_key: str


@dataclass(slots=True)
class OAuthProviderInterface:
    id: OAuthProviderId
    name: str
    login: Callable[[OAuthLoginCallbacks], Awaitable[OAuthCredentials]]
    refresh_token: Callable[[OAuthCredentials], Awaitable[OAuthCredentials]]
    get_api_key: Callable[[OAuthCredentials], str]
    uses_callback_server: bool = False
    modify_models: Callable[[list[Model], OAuthCredentials], list[Model]] | None = None


@dataclass(slots=True)
class _TokenSuccess:
    access: str
    refresh: str
    expires: int


class _OAuthServerProtocol:
    async def wait_for_code(self) -> str | None:  # pragma: no cover - protocol-like runtime helper
        raise NotImplementedError

    def cancel_wait(self) -> None:  # pragma: no cover - protocol-like runtime helper
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - protocol-like runtime helper
        raise NotImplementedError


@dataclass(slots=True)
class _LocalOAuthServer(_OAuthServerProtocol):
    server: asyncio.AbstractServer
    wait_future: asyncio.Future[str | None]

    async def wait_for_code(self) -> str | None:
        return await self.wait_future

    def cancel_wait(self) -> None:
        if not self.wait_future.done():
            self.wait_future.set_result(None)

    async def close(self) -> None:
        self.server.close()
        await self.server.wait_closed()


@dataclass(slots=True)
class _ManualOnlyOAuthServer(_OAuthServerProtocol):
    async def wait_for_code(self) -> str | None:
        return None

    def cancel_wait(self) -> None:
        return None

    async def close(self) -> None:
        return None


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


async def generate_pkce() -> tuple[str, str]:
    verifier = _base64url_encode(secrets.token_bytes(32))
    challenge = _base64url_encode(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def _oauth_success_html(message: str) -> str:
    return _render_oauth_page(
        title="Authentication successful",
        heading="Authentication successful",
        message=message,
    )


def _oauth_error_html(message: str, details: str | None = None) -> str:
    return _render_oauth_page(
        title="Authentication failed",
        heading="Authentication failed",
        message=message,
        details=details,
    )


def _render_oauth_page(
    *, title: str, heading: str, message: str, details: str | None = None
) -> str:
    def escape_html(value: str) -> str:
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;")
        )

    details_markup = (
        (
            '<div style="margin-top:16px;font-family:ui-monospace,monospace;'
            'font-size:13px;color:#a1a1aa;white-space:pre-wrap">'
            f"{escape_html(details)}"
            "</div>"
        )
        if details
        else ""
    )
    styles = (
        "html{color-scheme:dark}"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "padding:24px;background:#09090b;color:#fafafa;font-family:ui-sans-serif,system-ui,sans-serif;"
        "text-align:center}"
        "main{max-width:560px}"
        "h1{margin:0 0 10px;font-size:28px;line-height:1.15}"
        "p{margin:0;line-height:1.7;color:#a1a1aa;font-size:15px}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f"<title>{escape_html(title)}</title>"
        f"<style>{styles}</style>"
        "</head><body><main>"
        f"<h1>{escape_html(heading)}</h1>"
        f"<p>{escape_html(message)}</p>{details_markup}</main></body></html>"
    )


def _create_state() -> str:
    return secrets.token_hex(16)


def parse_openai_codex_authorization_input(input_value: str) -> tuple[str | None, str | None]:
    value = input_value.strip()
    if not value:
        return None, None

    try:
        parsed = urlparse(value)
    except ValueError:
        parsed = None

    if parsed is not None and (parsed.scheme or parsed.netloc):
        query = parse_qs(parsed.query)
        return _first(query.get("code")), _first(query.get("state"))

    if "#" in value:
        code, state = value.split("#", 1)
        return code or None, state or None

    if "code=" in value:
        query = parse_qs(value)
        return _first(query.get("code")), _first(query.get("state"))

    return value, None


def extract_openai_codex_account_id(token: str) -> str:
    try:
        payload = _decode_jwt_payload(token)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Failed to extract account_id from token") from exc

    auth = payload.get(OPENAI_AUTH_CLAIM_PATH)
    if not isinstance(auth, dict):
        raise ValueError("Failed to extract account_id from token")
    account_id = auth.get("chatgpt_account_id")
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("Failed to extract account_id from token")
    return account_id


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token")
    payload = json.loads(_base64url_decode(parts[1]).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid token payload")
    return payload


async def _exchange_openai_codex_authorization_code(
    code: str,
    verifier: str,
    *,
    redirect_uri: str = REDIRECT_URI,
) -> _TokenSuccess:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": redirect_uri,
            },
        )
    if not response.is_success:
        text = response.text
        print(
            f"[openai-codex] code->token failed: {response.status_code} {text}",
            file=sys.stderr,
        )
        raise RuntimeError("Token exchange failed")

    payload = response.json()
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if (
        not isinstance(access, str)
        or not isinstance(refresh, str)
        or not isinstance(expires_in, int)
    ):
        print(f"[openai-codex] token response missing fields: {payload}", file=sys.stderr)
        raise RuntimeError("Token exchange failed")

    return _TokenSuccess(
        access=access,
        refresh=refresh,
        expires=int(expires_in * 1000 + _now_ms()),
    )


async def refresh_openai_codex_token(refresh_token: str) -> OAuthCredentials:
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                TOKEN_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": CLIENT_ID,
                },
            )
        except Exception as exc:
            print(f"[openai-codex] Token refresh error: {exc}", file=sys.stderr)
            raise RuntimeError("Failed to refresh OpenAI Codex token") from exc

    if not response.is_success:
        print(
            f"[openai-codex] Token refresh failed: {response.status_code} {response.text}",
            file=sys.stderr,
        )
        raise RuntimeError("Failed to refresh OpenAI Codex token")

    payload = response.json()
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    if (
        not isinstance(access, str)
        or not isinstance(refresh, str)
        or not isinstance(expires_in, int)
    ):
        print(f"[openai-codex] Token refresh response missing fields: {payload}", file=sys.stderr)
        raise RuntimeError("Failed to refresh OpenAI Codex token")

    return OAuthCredentials(
        access=access,
        refresh=refresh,
        expires=int(expires_in * 1000 + _now_ms()),
        account_id=extract_openai_codex_account_id(access),
    )


async def _create_openai_codex_authorization_flow(
    originator: str = DEFAULT_OPENAI_CODEX_ORIGINATOR,
) -> tuple[str, str, str]:
    verifier, challenge = await generate_pkce()
    state = _create_state()

    url = httpx.URL(AUTHORIZE_URL).copy_merge_params(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": originator,
        }
    )
    return verifier, state, str(url)


async def _start_openai_codex_oauth_server(state: str) -> _OAuthServerProtocol:
    loop = asyncio.get_running_loop()
    wait_future: asyncio.Future[str | None] = loop.create_future()

    async def handle_connection(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        response_body = _oauth_error_html("Internal error while processing OAuth callback.")
        status = "500 Internal Server Error"
        try:
            request_line = await reader.readline()
            while True:
                line = await reader.readline()
                if line in {b"", b"\n", b"\r\n"}:
                    break

            parts = request_line.decode("utf-8", errors="replace").strip().split()
            target = parts[1] if len(parts) >= 2 else "/"
            parsed = urlparse(target)

            if parsed.path != "/auth/callback":
                status = "404 Not Found"
                response_body = _oauth_error_html("Callback route not found.")
            else:
                query = parse_qs(parsed.query)
                query_state = _first(query.get("state"))
                if query_state != state:
                    status = "400 Bad Request"
                    response_body = _oauth_error_html("State mismatch.")
                else:
                    code = _first(query.get("code"))
                    if not code:
                        status = "400 Bad Request"
                        response_body = _oauth_error_html("Missing authorization code.")
                    else:
                        status = "200 OK"
                        response_body = _oauth_success_html(
                            "OpenAI authentication completed. You can close this window."
                        )
                        if not wait_future.done():
                            wait_future.set_result(code)
        except Exception:
            status = "500 Internal Server Error"
            response_body = _oauth_error_html("Internal error while processing OAuth callback.")
        finally:
            body_bytes = response_body.encode("utf-8")
            writer.write(
                (
                    f"HTTP/1.1 {status}\r\n"
                    "Content-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body_bytes)}\r\n"
                    "Connection: close\r\n\r\n"
                ).encode()
                + body_bytes
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    try:
        server = await asyncio.start_server(handle_connection, host="127.0.0.1", port=1455)
    except OSError as exc:
        code = getattr(exc, "errno", None) or exc.__class__.__name__
        print(
            "[openai-codex] Failed to bind http://127.0.0.1:1455 "
            f"({code}) Falling back to manual paste.",
            file=sys.stderr,
        )
        return _ManualOnlyOAuthServer()

    return _LocalOAuthServer(server=server, wait_future=wait_future)


async def login_openai_codex(
    *,
    on_auth: Callable[[OAuthAuthInfo], None],
    on_prompt: Callable[[OAuthPrompt], Awaitable[str]],
    on_progress: Callable[[str], None] | None = None,
    on_manual_code_input: Callable[[], Awaitable[str]] | None = None,
    originator: str = DEFAULT_OPENAI_CODEX_ORIGINATOR,
) -> OAuthCredentials:
    del on_progress

    verifier, state, url = await _create_openai_codex_authorization_flow(originator)
    server = await _start_openai_codex_oauth_server(state)

    on_auth(
        OAuthAuthInfo(
            url=url,
            instructions="A browser window should open. Complete login to finish.",
        )
    )

    manual_task: asyncio.Task[str] | None = None
    code: str | None = None

    try:
        if on_manual_code_input is not None:
            manual_task = asyncio.create_task(_await_manual_code_input(on_manual_code_input))
            wait_task = asyncio.create_task(server.wait_for_code())
            done, pending = await asyncio.wait(
                {manual_task, wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            if wait_task in done:
                code = wait_task.result()
                if manual_task is not None:
                    manual_task.cancel()
                    await asyncio.gather(manual_task, return_exceptions=True)
            else:
                server.cancel_wait()
                manual_value = manual_task.result()
                parsed_code, parsed_state = parse_openai_codex_authorization_input(manual_value)
                if parsed_state and parsed_state != state:
                    raise RuntimeError("State mismatch")
                code = parsed_code
                wait_task.cancel()
                await asyncio.gather(wait_task, return_exceptions=True)

            for task in pending:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        else:
            code = await server.wait_for_code()

        if not code:
            prompt_value = await on_prompt(
                OAuthPrompt(message="Paste the authorization code (or full redirect URL):")
            )
            parsed_code, parsed_state = parse_openai_codex_authorization_input(prompt_value)
            if parsed_state and parsed_state != state:
                raise RuntimeError("State mismatch")
            code = parsed_code

        if not code:
            raise RuntimeError("Missing authorization code")

        token = await _exchange_openai_codex_authorization_code(code, verifier)
        return OAuthCredentials(
            access=token.access,
            refresh=token.refresh,
            expires=token.expires,
            account_id=extract_openai_codex_account_id(token.access),
        )
    finally:
        if manual_task is not None and not manual_task.done():
            manual_task.cancel()
            await asyncio.gather(manual_task, return_exceptions=True)
        await server.close()


def _get_openai_codex_api_key(credentials: OAuthCredentials) -> str:
    return credentials.access


async def _login_openai_codex_with_callbacks(callbacks: OAuthLoginCallbacks) -> OAuthCredentials:
    return await login_openai_codex(
        on_auth=callbacks.on_auth,
        on_prompt=callbacks.on_prompt,
        on_progress=callbacks.on_progress,
        on_manual_code_input=callbacks.on_manual_code_input,
    )


async def _refresh_openai_codex_credentials(credentials: OAuthCredentials) -> OAuthCredentials:
    return await refresh_openai_codex_token(credentials.refresh)


openai_codex_oauth_provider = OAuthProviderInterface(
    id=OPENAI_CODEX_PROVIDER_ID,
    name="ChatGPT Plus/Pro (Codex Subscription)",
    uses_callback_server=True,
    login=_login_openai_codex_with_callbacks,
    refresh_token=_refresh_openai_codex_credentials,
    get_api_key=_get_openai_codex_api_key,
)

_BUILT_IN_OAUTH_PROVIDERS: list[OAuthProviderInterface] = [openai_codex_oauth_provider]
_oauth_provider_registry: dict[str, OAuthProviderInterface] = {
    provider.id: provider for provider in _BUILT_IN_OAUTH_PROVIDERS
}


def get_oauth_provider(provider_id: OAuthProviderId) -> OAuthProviderInterface | None:
    return _oauth_provider_registry.get(provider_id)


def register_oauth_provider(provider: OAuthProviderInterface) -> None:
    _oauth_provider_registry[provider.id] = provider


def unregister_oauth_provider(provider_id: OAuthProviderId) -> None:
    built_in = next(
        (provider for provider in _BUILT_IN_OAUTH_PROVIDERS if provider.id == provider_id), None
    )
    if built_in is not None:
        _oauth_provider_registry[provider_id] = built_in
        return
    _oauth_provider_registry.pop(provider_id, None)


def reset_oauth_providers() -> None:
    _oauth_provider_registry.clear()
    for provider in _BUILT_IN_OAUTH_PROVIDERS:
        _oauth_provider_registry[provider.id] = provider


def get_oauth_providers() -> list[OAuthProviderInterface]:
    return list(_oauth_provider_registry.values())


def get_oauth_provider_info_list() -> list[OAuthProviderInfo]:
    return [
        OAuthProviderInfo(id=provider.id, name=provider.name) for provider in get_oauth_providers()
    ]


async def refresh_oauth_token(
    provider_id: OAuthProviderId,
    credentials: OAuthCredentials,
) -> OAuthCredentials:
    provider = get_oauth_provider(provider_id)
    if provider is None:
        raise LookupError(f"Unknown OAuth provider: {provider_id}")
    return await provider.refresh_token(credentials)


async def get_oauth_api_key(
    provider_id: OAuthProviderId,
    credentials: dict[str, OAuthCredentials],
) -> OAuthApiKeyResult | None:
    provider = get_oauth_provider(provider_id)
    if provider is None:
        raise LookupError(f"Unknown OAuth provider: {provider_id}")

    provider_credentials = credentials.get(provider_id)
    if provider_credentials is None:
        return None

    if _now_ms() >= provider_credentials.expires:
        try:
            provider_credentials = await provider.refresh_token(provider_credentials)
        except Exception as exc:
            raise RuntimeError(f"Failed to refresh OAuth token for {provider_id}") from exc

    return OAuthApiKeyResult(
        new_credentials=provider_credentials,
        api_key=provider.get_api_key(provider_credentials),
    )


def build_openai_codex_user_agent() -> str:
    return f"epsilon ({platform.system()} {platform.release()}; {platform.machine()})"


def _first(values: list[str] | None) -> str | None:
    if not values:
        return None
    return values[0]


def _now_ms() -> int:
    import time

    return int(time.time() * 1000)


async def _await_manual_code_input(callback: Callable[[], Awaitable[str]]) -> str:
    return await callback()


__all__ = [
    "DEFAULT_OPENAI_CODEX_ORIGINATOR",
    "OPENAI_CODEX_PROVIDER_ID",
    "OAuthApiKeyResult",
    "OAuthAuthInfo",
    "OAuthCredentials",
    "OAuthLoginCallbacks",
    "OAuthPrompt",
    "OAuthProviderId",
    "OAuthProviderInfo",
    "OAuthProviderInterface",
    "build_openai_codex_user_agent",
    "extract_openai_codex_account_id",
    "generate_pkce",
    "get_oauth_api_key",
    "get_oauth_provider",
    "get_oauth_provider_info_list",
    "get_oauth_providers",
    "login_openai_codex",
    "openai_codex_oauth_provider",
    "parse_openai_codex_authorization_input",
    "refresh_oauth_token",
    "refresh_openai_codex_token",
    "register_oauth_provider",
    "reset_oauth_providers",
    "unregister_oauth_provider",
]
