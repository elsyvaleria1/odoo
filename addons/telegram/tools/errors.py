"""What a Bot API call's failure means for whoever sent it.

Telegram answers every failure with `{"ok": false, "error_code", "description",
"parameters"}`; the class says what to do next, so no caller reads error text.
"""

import re

_RETRY_AFTER = re.compile(r"retry after (\d+)", re.IGNORECASE)


class TelegramApiError(Exception):
    """A failure Telegram answered: its code and description."""

    retryable = False

    def __init__(self, error_code, description, parameters=None) -> None:
        super().__init__(f"{error_code}: {description}")
        self.error_code = error_code
        self.description = description or ""
        self.parameters = parameters or {}


class TelegramRetryAfter(TelegramApiError):
    """Flood control: try again after `seconds`."""

    retryable = True

    @property
    def seconds(self) -> int:
        seconds = self.parameters.get("retry_after")
        if seconds is None and (match := _RETRY_AFTER.search(self.description)):
            seconds = int(match.group(1))
        return int(seconds or 5)


class TelegramForbidden(TelegramApiError):
    """The bot may not write there any more: blocked, kicked, deactivated."""


class TelegramParseError(TelegramApiError):
    """The formatted text did not parse; the same text sent plain would."""


class TelegramChatMigrated(TelegramApiError):
    """The group became a supergroup under a new chat id."""

    @property
    def new_chat_id(self) -> str:
        return str(self.parameters.get("migrate_to_chat_id") or "")


class TelegramNotFound(TelegramApiError):
    """The chat or the message the call names does not exist (any more)."""


class TelegramBadRequest(TelegramApiError):
    """Any other refusal: the request itself is wrong and resending it is not."""


class TelegramUnavailable(TelegramApiError):
    """Telegram failed on its side (5xx) or could not be reached."""

    retryable = True


def classify(body):
    code = body.get("error_code") or 0
    description = body.get("description") or ""
    parameters = body.get("parameters") or {}
    lowered = description.lower()
    if parameters.get("migrate_to_chat_id"):
        cls = TelegramChatMigrated
    elif code == 429 or parameters.get("retry_after"):
        cls = TelegramRetryAfter
    elif code == 403:
        cls = TelegramForbidden
    elif code >= 500:
        cls = TelegramUnavailable
    elif "can't parse entities" in lowered or "can't find end of" in lowered:
        cls = TelegramParseError
    elif "not found" in lowered:
        cls = TelegramNotFound
    else:
        cls = TelegramBadRequest
    return cls(code, description, parameters)
