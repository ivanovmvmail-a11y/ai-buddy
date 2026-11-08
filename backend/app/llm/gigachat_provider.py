from gigachat import GigaChat

from app.config import settings

from .base import Message


class GigaChatProvider:
    name = "gigachat"

    def __init__(self) -> None:
        if not settings.gigachat_credentials:
            raise RuntimeError("GIGACHAT_CREDENTIALS не задан в backend/.env")
        kwargs: dict = {
            "credentials": settings.gigachat_credentials,
            "scope": settings.gigachat_scope,
            "model": settings.gigachat_model,
            "timeout": 60,
        }
        if settings.gigachat_ca_bundle_file:
            kwargs["ca_bundle_file"] = settings.gigachat_ca_bundle_file
        else:
            kwargs["verify_ssl_certs"] = settings.gigachat_verify_ssl
        self._client = GigaChat(**kwargs)

    async def chat(self, messages: list[Message]) -> str:
        response = await self._client.achat({"messages": [m.model_dump() for m in messages]})
        return response.choices[0].message.content
