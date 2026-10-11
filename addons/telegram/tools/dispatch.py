import logging
import time
from dataclasses import dataclass
from functools import wraps

from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.tools.translate import LazyGettext

_logger = logging.getLogger(__name__)

TIERS = ("unlinked", "partner", "internal")
COMPANY_MODES = ("any", "choose")


@dataclass(frozen=True)
class TelegramCommand:
    """A command a handler answers: the method, who may use it, whether it
    opens a multi-step flow (refused while another flow is open), and whether
    every bot running the handler answers it without the command being linked
    to the bot.

    Who may use it is declared, so that running it, /ayuda and the command
    menu Telegram shows each person ask the same question: the tier, then for
    an internal user the `access` (model, operation) they have in Odoo -- the
    ir.access rows, not a group test -- then the handler's `_command_allowed`.
    `description` is the menu's line for it; a command without one is not in
    the menu, and still runs. `company` says which company it acts in
    (COMPANY_MODES)."""

    method: str
    tier: str = "internal"
    starts_flow: bool = False
    builtin: bool = False
    access: tuple[str, str] | None = None
    description: LazyGettext | None = None
    company: str = "any"

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise ValueError(f"unknown tier {self.tier!r}")
        if self.company not in COMPANY_MODES:
            raise ValueError(f"unknown company mode {self.company!r}")
        if self.access and self.tier != "internal":
            raise ValueError("access is an internal user's, tier internal")


def translation_env(bot, chat=None):
    env = bot.env
    lang = bot.get_lang(chat)
    if lang and lang != env.lang:
        env = env(context={**env.context, "lang": lang})
    return env


def message_kind(message) -> str:
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
