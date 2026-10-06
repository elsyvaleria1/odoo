import itertools
import re
from collections.abc import Callable, Iterable, Iterator

__all__ = [
    "pattern_to_translated_trigram_patterns",
    "value_to_translated_trigram_patterns",
]


_JSON_ESCAPED_RE = re.compile(r'(["\\\x00-\x1f])')
_JSON_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
} | {
    chr(code): f"\\u{code:04x}" for code in range(0x20) if chr(code) not in "\b\f\n\r\t"
}
_WILDCARD_ESCAPE_RE = re.compile(r"(_|%|\\)")
_READ_RAW = '"\\'
_MIN_FRAGMENT = 3
_MAX_ALTERNATIVES = 4


def _identity(text: str) -> str:
    return text


def _like_escape(text: str) -> str:
    return _WILDCARD_ESCAPE_RE.sub(r"\\\1", text)


def _literal_runs(pattern: str) -> Iterator[str]:
    run: list[str] = []
    escaped = False
    for char in pattern:
        if escaped:
            run.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char in "%_":
            yield "".join(run)
            run = []
        else:
            run.append(char)
    if escaped:
        run.append("\\")
    yield "".join(run)


def _translated_trigram_patterns(
    runs: Iterable[str], unaccent: Callable[[str], str], unaccented: bool
) -> tuple[str, ...]:
    kept = [run for run in runs if len(run) >= _MIN_FRAGMENT]
    if not kept:
        return ()
    segments: list[tuple[str, ...]] = []
    alternated = 0
    for run in kept:
        if segments:
            segments.append(("%",))
        previous = ""
        for index, part in enumerate(_JSON_ESCAPED_RE.split(run)):
            if index % 2 == 0:
                if part:
                    text = part if unaccented else unaccent(part)
                    segments.append((_like_escape(text),))
                    previous = text[-1:]
                continue
            escape = _like_escape(_JSON_ESCAPES[part])
            if not unaccented or part not in _READ_RAW:
                segments.append((escape,))
            elif previous.isalnum() and 2 ** (alternated + 1) <= _MAX_ALTERNATIVES:
                # both readings keep the word before the character bounded, so
                # its padded trigrams stay in the index condition
                alternated += 1
                segments.append((escape, _like_escape(part)))
            else:
                # both readings end with the character itself
                wildcard = "%" if previous else ""
                segments.append((f"{wildcard}{_like_escape(part)}",))
            previous = part
    return tuple(
        dict.fromkeys(f"%{''.join(combo)}%" for combo in itertools.product(*segments))
    )


def value_to_translated_trigram_patterns(
    value: str, unaccent: Callable[[str], str] = _identity
) -> tuple[str, ...]:
    return _translated_trigram_patterns([value], unaccent, unaccented=False)


def pattern_to_translated_trigram_patterns(
    pattern: str,
    unaccent: Callable[[str], str] = _identity,
    *,
    unaccent_pattern: bool = False,
) -> tuple[str, ...]:
    if unaccent_pattern:
        pattern = unaccent(pattern)
    return _translated_trigram_patterns(
        _literal_runs(pattern), unaccent, unaccented=unaccent_pattern
    )
