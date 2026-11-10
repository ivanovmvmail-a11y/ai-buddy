"""Доменные ошибки; чужой объект неотличим от отсутствующего."""


class NotFound(Exception):
    def __init__(self):
        super().__init__("Не найдено")


class Forbidden(Exception):
    def __init__(self, message="Действие запрещено"):
        super().__init__(message)


class Conflict(Exception):
    def __init__(self, message="Неверный переход статуса"):
        super().__init__(message)
