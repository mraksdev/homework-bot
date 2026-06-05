class NotCorrectResponseError(Exception):
    """Raised when API returns unexpected response."""


class TelegramSendError(Exception):
    """Raised when sending message to Telegram fails."""
