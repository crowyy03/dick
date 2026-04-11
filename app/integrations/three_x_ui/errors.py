class PanelError(Exception):
    pass


class PanelAuthError(PanelError):
    pass


class PanelNotFoundError(PanelError):
    pass


class PanelBadRequestError(PanelError):
    pass


class PanelTransientError(PanelError):
    """Network / 5xx — safe to retry."""

    pass


class PanelClientVerificationError(PanelError):
    """Клиент не найден в inbound после addClient (или выключен)."""

    pass


class PanelShareLinkError(PanelError):
    """Не удалось собрать vless:// из данных inbound (протокол/JSON/хост)."""

    pass
