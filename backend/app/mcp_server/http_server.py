"""MCP онбординга по сети: Streamable HTTP (спека 005, изменение 13.11).

stdio-вариант (`server.py main`) — один пользователь на процесс, для Claude Desktop/IDE. Веб-агенту нужен один
сетевой сервер на всех пользователей, как MCP-серверы корпоративных сервисов за MCP Hub:

- `POST /mcp` — протокол MCP (Streamable HTTP, JSON-ответы, без состояния между запросами);
- `Authorization: Bearer <MCP_SERVICE_TOKEN>` — сервер принимает вызовы только от доверенного backend агента;
- `X-AI-Buddy-User: <id>` — от чьего имени вызов. Пользователя задаёт backend по сессии входа (в Авито — SSO),
  не модель: аргументов «от имени кого» у инструментов нет. Права проверяют те же сервисы, что и в stdio.
- `GET /health` — для healthcheck Docker.

Запуск: `python -m app.mcp_server.http_server` (порт MCP_PORT, по умолчанию 8001).
"""
import hmac
import logging
import os
from contextlib import AsyncExitStack

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from app.agent.users import DEMO_USERS
from app.async_runner import run

from . import storage
from .server import create_server

log = logging.getLogger("ai_buddy.mcp.http")
USER_HEADER = b"x-ai-buddy-user"


async def _reply(send, status: int, text: str) -> None:
    body = text.encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/plain; charset=utf-8"), (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


def create_app(token: str):
    """ASGI-приложение: по менеджеру MCP-сессий на каждого демо-пользователя (сервер знает своего пользователя)."""
    if not token:
        raise ValueError("Задайте MCP_SERVICE_TOKEN: без него сервер принял бы вызов от кого угодно")
    managers = {user_id: StreamableHTTPSessionManager(create_server(user_id)._mcp_server, json_response=True,
                                                      stateless=True)
                for user_id in DEMO_USERS}
    expected = f"Bearer {token}".encode()
    stack = AsyncExitStack()

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    for manager in managers.values():
                        await stack.enter_async_context(manager.run())
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await stack.aclose()
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        path = scope["path"].rstrip("/")
        if path == "/health":
            return await _reply(send, 200, "ok")
        if path != "/mcp":
            return await _reply(send, 404, "Not found")
        headers = dict(scope["headers"])
        if not hmac.compare_digest(headers.get(b"authorization", b""), expected):
            return await _reply(send, 401, "Unauthorized")
        user_id = headers.get(USER_HEADER, b"").decode("utf-8", "replace")
        manager = managers.get(user_id)
        if manager is None:
            return await _reply(send, 403, "Unknown user")
        log.info("mcp http user=%s", user_id)
        await manager.handle_request(scope, receive, send)

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(os.environ.get("MCP_SERVICE_TOKEN", ""))
    config = uvicorn.Config(app, host=os.environ.get("MCP_HOST", "0.0.0.0"), port=int(os.environ.get("MCP_PORT", "8001")),
                            log_level="info", lifespan="on")
    # Тот же общий event loop, что у сервисов (async_runner): соединения PostgreSQL привязаны к одному loop.
    try:
        run(uvicorn.Server(config).serve(), timeout=None)
    finally:
        run(storage.get_store().close())


if __name__ == "__main__":
    main()
