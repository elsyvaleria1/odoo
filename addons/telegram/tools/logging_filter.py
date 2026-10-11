import logging
import re

_TOKEN_PATTERN = re.compile(r"(\d{5,12}):([A-Za-z0-9_-]{15,60})")


def _mask_token(match: re.Match) -> str:
    bot_id = match.group(1)
    secret = match.group(2)
    if len(secret) > 4:
        return f"{bot_id}:***...{secret[-4:]}"
    return f"{bot_id}:****"


class TelegramTokenFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            try:
                args = (
                    list(record.args)
                    if isinstance(record.args, tuple)
                    else [record.args]
                )
                masked_args = []
                for arg in args:
                    if isinstance(arg, str):
                        masked_args.append(_TOKEN_PATTERN.sub(_mask_token, arg))
                    else:
                        masked_args.append(arg)
                record.args = tuple(masked_args)
            except Exception:
                pass

        if isinstance(record.msg, str):
            record.msg = _TOKEN_PATTERN.sub(_mask_token, record.msg)

        return True


ACCESS_LOGGERS = ("odoo.service.http.access", "werkzeug")


def install_token_filter() -> None:
    for name in ACCESS_LOGGERS:
        logger = logging.getLogger(name)
        if not any(isinstance(f, TelegramTokenFilter) for f in logger.filters):
            logger.addFilter(TelegramTokenFilter())


def register_with_integration() -> None:
    from odoo.addons.integration.tools import register_url_secret

    register_url_secret(_TOKEN_PATTERN, _mask_token)
