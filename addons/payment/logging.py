import contextlib
import logging
import re
from collections.abc import Mapping

from odoo.libs import redact

# Every record of a payment logger is masked, and the cost grows with its
# length: past this many characters a message is cut, with a marker saying so.
# A provider's own payload, pretty-printed, stays far below it.
MESSAGE_LIMIT = 65536
_WALK_DEPTH = 50
_WALKED = (Mapping, list, tuple, set, frozenset)


class SensitiveDataFilter(logging.Filter):
    # Masks the record as it will be emitted. The provider's own keys, which may
    # be named in no way libs.redact knows, are masked in the args first,
    # whatever their value's type, then the formatted message, traceback and
    # stack are masked as text: libs.redact's secrets plus those keys. The keys
    # are a set a provider module may still populate after the filter is built.
    def __init__(self, sensitive_keys=None) -> None:
        super().__init__()
        self._sensitive_keys = set() if sensitive_keys is None else sensitive_keys

    def filter(self, record):
        # a filter runs outside logging's error handling: what raises here
        # raises into the caller's log call, so a record that cannot be masked
        # is emptied instead, never passed on as it is
        try:
            self._mask_record(record, frozenset(map(str, self._sensitive_keys)))
        except Exception as error:
            record.msg = f"<payment log record dropped: masking it failed ({type(error).__name__})>"
            record.args = ()
            record.exc_info = record.exc_text = record.stack_info = None
        return True

    @staticmethod
    def _mask_record(record, keys):
        if isinstance(record.args, Mapping):
            # "%(password)s" % {...}: the formatted text keeps the value
            # without the key that names it, so the key is read here
            record.args = redact.mask_data(record.args)
        if keys and record.args:
            # args that cannot be walked stay as they are, for the text pass
            # below to mask
            with contextlib.suppress(Exception):
                record.args = _mask_keys(record.args, keys, set())
        try:
            message = record.getMessage()
            formatted = True
        except Exception:
            # logging's handleError would print the raw msg and args
            message, formatted = _unformatted(record), False
        masked = _mask(message, keys)
        if masked != message or not formatted:
            record.msg, record.args = masked, ()
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = logging.Formatter().formatException(record.exc_info)
            # Every formatter renders exc_text once it is set; the exc_info left
            # behind would hand the raw traceback, frames and locals included,
            # to any handler reading the exception itself.
            record.exc_info = None
        if record.exc_text:
            record.exc_text = _mask(record.exc_text, keys)
        if record.stack_info:
            record.stack_info = _mask(record.stack_info, keys)


def _unformatted(record):
    try:
        message = str(record.msg)
    except Exception:
        message = f"<unformattable {type(record.msg).__name__} message>"
    if not record.args:
        return message
    try:
        return f"{message} [unformattable args: {record.args!r}]"
    except Exception:
        return f"{message} [unformattable args]"


def _mask(text, keys):
    if len(text) <= MESSAGE_LIMIT:
        return _mask_card_numbers(redact.mask_text(text, keys=keys))
    omitted = len(text) - MESSAGE_LIMIT
    masked = _mask_card_numbers(redact.mask_text(text, MESSAGE_LIMIT, keys=keys))
    return f"{masked}\n... [{omitted} more characters not logged]"


# a card number under no key at all (a provider's echo, a traceback's locals):
# 13 to 19 digits, grouped by spaces or dashes, passing the Luhn check, keeps
# its last four as the masked label the providers themselves show
_CARD_NUMBER = re.compile(r"(?<![\d-])\d(?:[ -]?\d){12,18}(?![\d-])")


def _mask_card_numbers(text):
    return _CARD_NUMBER.sub(_mask_card_number, text)


def _mask_card_number(match):
    digits = "".join(filter(str.isdigit, match[0]))
    if not _passes_luhn(digits):
        return match[0]
    return f"****{digits[-4:]}"


def _passes_luhn(digits):
    total = 0
    for index, digit in enumerate(reversed(digits)):
        value = int(digit) * (2 if index % 2 else 1)
        total += value - 9 if value > 9 else value
    return total % 10 == 0


def _mask_keys(data, keys, active):
    if not isinstance(data, _WALKED) or id(data) in active or len(active) > _WALK_DEPTH:
        return data
    active.add(id(data))
    try:
        if isinstance(data, Mapping):
            masked = {
                key: redact.MASK if key in keys else _mask_keys(value, keys, active)
                for key, value in data.items()
            }
            if all(masked[key] is value for key, value in data.items()):
                return data
            return masked
        items = [_mask_keys(item, keys, active) for item in data]
        if all(new is old for new, old in zip(items, data, strict=True)):
            return data
        if isinstance(data, list):
            return items
        if isinstance(data, tuple):
            return tuple(items)
        return frozenset(items) if isinstance(data, frozenset) else set(items)
    finally:
        active.discard(id(data))


def get_payment_logger(name, sensitive_keys=None):
    """Return the logger of a payment module, masking what it would leak.

    :param str name: The name of the logger.
    :param set sensitive_keys: Keys of the provider's payment data that are secret under a
        name the generic redaction does not recognise.
    :return: The logger.
    :rtype: logging.Logger
    """
    logger = logging.getLogger(name)
    logger.addFilter(SensitiveDataFilter(sensitive_keys))
    return logger
