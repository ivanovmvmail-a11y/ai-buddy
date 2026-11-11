"""Тело HTTP-запроса: только JSON-объект. Битый JSON — понятная 400, а не «Field required» (аудит, мелочи)."""
from flask import request


class BadBody(Exception):
    pass


def json_body() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        if request.get_data(cache=True).strip():
            raise BadBody("Тело запроса — не JSON")
        return {}
    if not isinstance(data, dict):
        raise BadBody("Ожидается JSON-объект")
    return data
