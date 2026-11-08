from pathlib import Path

from gigachat import GigaChat

from app.config import settings

from .base import Message

# Публичный корневой сертификат Минцифры (https://www.gosuslugi.ru/crt), лежит в репозитории.
DEFAULT_CA_FILE = Path(__file__).resolve().parents[2] / "certs" / "russian_trusted_root_ca.cer"


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
        ca_file = settings.gigachat_ca_bundle_file or (str(DEFAULT_CA_FILE) if DEFAULT_CA_FILE.exists() else "")
        if ca_file:
            # с сертификатом проверка SSL всегда включена, GIGACHAT_VERIFY_SSL игнорируется
            kwargs["ca_bundle_file"] = ca_file
        else:
            kwargs["verify_ssl_certs"] = settings.gigachat_verify_ssl
        self._client = GigaChat(**kwargs)

    async def chat(self, messages: list[Message]) -> str:
        response = await self._client.achat({"messages": [m.model_dump() for m in messages]})
        return response.choices[0].message.content
