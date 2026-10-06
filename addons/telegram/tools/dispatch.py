import logging
import time
from dataclasses import dataclass
from functools import wraps

from odoo.db.errors import PG_RETRY_EXCEPTIONS

_logger = logging.getLogger(__name__)

TIERS = ("unlinked", "partner", "internal")


@dataclass(frozen=True)
class TelegramCommand:
    """A command a handler answers: the method, who may use it, whether it
    opens a multi-step flow (refused while another flow is open), and whether
    every bot answers it without the command being linked to the bot."""

    method: str
    tier: str = "internal"
    starts_flow: bool = False
    builtin: bool = False

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}")


def translation_env(bot, chat=None):
    env = bot.env
    lang = bot.get_lang(chat)
    if lang and lang != env.lang:
        env = env(context={**env.context, "lang": lang})
    return env


def message_kind(message) -> str:
    """What a non-command message carries, as the router routes it."""
    if message.get("voice") or message.get("audio"):
        return "voice"
    if message.get("photo"):
        return "photo"
    if message.get("document") or message.get("video"):
        return "document"
    if message.get("contact"):
        return "contact"
    if message.get("location"):
        return "location"
    return "text"


def log_command_execution(func):
    @wraps(func)
    def wrapper(self, bot, chat, args, partner=False, internal_user=False):
        command_name = func.__name__.replace("_handle_", "").replace("_command", "")
        _logger.info("Executing command '%s' for chat %s", command_name, chat.id)
        start_time = time.time()
        try:
            result = func(self, bot, chat, args, partner, internal_user)
        except PG_RETRY_EXCEPTIONS:
            # Retryable conflict, not a failure: the request retry loop replays
            # the command on a fresh transaction. A traceback here reports as
            # broken a command that ends up succeeding.
            _logger.info(
                "Command '%s' hit a concurrency conflict after %.2fs, letting it retry",
                command_name,
                time.time() - start_time,
            )
            raise
        except Exception:
            _logger.exception(
                "Command '%s' failed after %.2fs",
                command_name,
                time.time() - start_time,
            )
            raise
        _logger.info(
            "Command '%s' completed successfully in %.2fs",
            command_name,
            time.time() - start_time,
        )
        return result

    return wrapper
