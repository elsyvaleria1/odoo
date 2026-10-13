from __future__ import annotations

import logging
import re
import shutil
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

import odoo.db
from odoo.libs.debug_log import DebugLog

from .._env import get_env_int

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import IO

    from _typeshed import SupportsRead

    from odoo.db import BaseCursor

_logger = logging.getLogger("odoo.service.db")
_debug = DebugLog(__name__)


_META_ARG_NONE = r"[ \t]*(?:\r?\n|\Z)"
_META_ARG_KEY = r"[ \t]+[A-Za-z0-9]+[ \t]*(?:\r?\n|\Z)"
_ALLOWED_PSQL_META_COMMANDS: dict[str, re.Pattern[str]] = {
    "\\.": re.compile(_META_ARG_NONE),
    "\\restrict": re.compile(_META_ARG_KEY),
    "\\unrestrict": re.compile(_META_ARG_KEY),
}

_COPY_WORD_MAX_LEN = 5
_CONFORMING_STRINGS = "STANDARD_CONFORMING_STRINGS"
_SQL_WORD_MAX_LEN = len(_CONFORMING_STRINGS)

_IDENT_START_ASCII = frozenset(string.ascii_letters + "_")
_IDENT_CONT_ASCII = frozenset(string.ascii_letters + string.digits + "_$")

_DOLLAR_TAG_RE = re.compile(
    r"\$(?:[A-Za-z_\x80-\U0010FFFF][A-Za-z0-9_\x80-\U0010FFFF]*)?\$"
)

_DEFAULT_MAX_SCAN_LINE = 64 * 1024 * 1024
_MIN_MAX_SCAN_LINE = 4 * 1024 * 1024


def _is_ident_start(c: str) -> bool:
    return c in _IDENT_START_ASCII or c >= "\x80"


def _is_ident_cont(c: str) -> bool:
    return c in _IDENT_CONT_ASCII or c >= "\x80"


class _PsqlSqlScanner:
    __slots__ = (
        "_ident_run_is_ident",
        "_ident_run_start",
        "_prev_word",
        "_quoted_word",
        "_setting_state",
        "_setting_violation",
        "_stmt_is_copy",
        "_stmt_seen_token",
        "_word",
        "_word_limit",
        "comment_depth",
        "copy_pending",
        "dollar_tag",
        "in_copy_data",
        "in_double_quote",
        "in_single_quote",
        "lineno",
        "single_quote_escaped",
    )

    def __init__(self) -> None:
        self.lineno = 1
        self._word = ""
        self._word_limit = _COPY_WORD_MAX_LEN
        self._setting_state = 0
        self._setting_violation: tuple[int, str] | None = None
        self._quoted_word = ""
        self._prev_word = ""
        self._stmt_seen_token = False
        self._stmt_is_copy = False
        self._ident_run_start = -1
        self._ident_run_is_ident = False
        self.in_copy_data = False
        self.copy_pending = False
        self.comment_depth = 0
        self.dollar_tag: str | None = None
        self.in_single_quote = False
        self.single_quote_escaped = False
        self.in_double_quote = False

    def at_statement_start(self) -> bool:
        return not (
            self._stmt_seen_token
            or self.in_copy_data
            or self.copy_pending
            or self.comment_depth
            or self.dollar_tag is not None
            or self.in_single_quote
            or self.in_double_quote
        )

    def _resume_carry_over(self, line: str, n: int) -> int:
        if self.comment_depth:
            return self._resume_block_comment(line, 0, n)
        if self.dollar_tag is not None:
            return self._resume_dollar_body(line, 0, n)
        if self.in_single_quote:
            return self._resume_single_quote(line, 0, n)
        if self.in_double_quote:
            return self._resume_double_quote(line, 0, n)
        return 0

    def _consume_copy_data(self, line: str) -> None:
        self.lineno += 1
        if line.rstrip("\n").rstrip("\r") == "\\.":
            self.in_copy_data = False
            self._reset_statement()

    def _absorb_ident_char(self, c: str, i: int) -> None:
        if self._ident_run_start < 0:
            self._ident_run_start = i
            self._ident_run_is_ident = _is_ident_start(c)
            self._word = c
        elif not self._ident_run_is_ident and _is_ident_start(c):
            self._flush_word()
            self._ident_run_start = i
            self._ident_run_is_ident = True
            self._word = c
        elif len(self._word) <= self._word_limit:
            self._word += c

    def _get_meta_command_violation(
        self, line: str, i: int, n: int
    ) -> tuple[int, str] | None:
        word = self._get_command_word(line, i, n)
        arg_pattern = _ALLOWED_PSQL_META_COMMANDS.get(word)
        if arg_pattern is None:
            return (self.lineno, word)
        if not arg_pattern.match(line, i + len(word)):
            end = line.find("\n", i)
            text = line[i:] if end == -1 else line[i:end]
            return (self.lineno, text.rstrip()[:80])
        return None

    def feed(self, line: str) -> tuple[int, str] | None:
        n = len(line)
        self._reset_ident_run()

        if self.in_copy_data:
            self._consume_copy_data(line)
            return self._setting_violation

        i = self._resume_carry_over(line, n)

        while i < n:
            c = line[i]
            if c == "\n":
                self._reset_ident_run()
                self.lineno += 1
                return self._setting_violation

            if c == "-" and i + 1 < n and line[i + 1] == "-":
                i = line.find("\n", i)
                if i == -1:
                    return self._setting_violation
                continue
            if c == "/" and i + 1 < n and line[i + 1] == "*":
                self.comment_depth = 1
                self._reset_ident_run()
                i = self._resume_block_comment(line, i + 2, n)
                continue
            if c == "$" and not self._is_identifier_continued():
                m = _DOLLAR_TAG_RE.match(line, i)
                if m:
                    self.dollar_tag = m.group(0)
                    self._reset_ident_run()
                    self._mark_opaque_token_seen()
                    self._setting_token("")
                    i = self._resume_dollar_body(line, m.end(), n)
                    continue
            if c == "'":
                self.in_single_quote = True
                self._quoted_word = ""
                self.single_quote_escaped = (
                    i > 0 and line[i - 1] in "Ee" and self._ident_run_start == i - 1
                )
                self._reset_ident_run()
                self._mark_opaque_token_seen()
                i = self._resume_single_quote(line, i + 1, n)
                continue
            if c == '"':
                self.in_double_quote = True
                self._quoted_word = ""
                self._reset_ident_run()
                self._mark_opaque_token_seen()
                i = self._resume_double_quote(line, i + 1, n)
                continue
            if c == "\\":
                violation = self._get_meta_command_violation(line, i, n)
                if violation is not None:
                    return violation
                self._reset_ident_run()
                self._mark_opaque_token_seen()
                i = line.find("\n", i)
                if i == -1:
                    return self._setting_violation
                continue

            if _is_ident_cont(c):
                self._absorb_ident_char(c, i)
            else:
                self._reset_ident_run()

            if c == "=":
                self._setting_token(c)
            if c == ";":
                if self.copy_pending:
                    self.copy_pending = False
                    self.in_copy_data = True
                self._reset_statement()
            i += 1
        self._reset_ident_run()
        return self._setting_violation

    def _setting_token(self, token: str, *, quoted: bool = False) -> None:
        word = token.upper()
        if quoted and word == _CONFORMING_STRINGS:
            self._setting_violation = (
                self.lineno,
                "standard_conforming_strings (named by a string literal)",
            )
            return
        state = self._setting_state
        if state == 0:
            self._setting_state = 1 if word == "SET" else -1
        elif state in (1, 2):
            if state == 1 and word in ("LOCAL", "SESSION"):
                self._setting_state = 2
            else:
                self._setting_state = 3 if word == _CONFORMING_STRINGS else -1
        elif state == 3:
            self._setting_state = 4 if word in ("=", "TO") else -1
        elif state == 4:
            if word not in ("ON", "TRUE", "YES", "1"):
                self._setting_violation = (
                    self.lineno,
                    "standard_conforming_strings = " + token[:32],
                )
            self._setting_state = -1
        self._word_limit = (
            _SQL_WORD_MAX_LEN if self._setting_state in (1, 2) else _COPY_WORD_MAX_LEN
        )

    def _is_identifier_continued(self) -> bool:
        return self._ident_run_is_ident

    def _reset_ident_run(self) -> None:
        self._ident_run_start = -1
        self._ident_run_is_ident = False
        self._flush_word()

    def _flush_word(self) -> None:
        word = self._word
        if not word:
            return
        self._word = ""
        if self._setting_state >= 0:
            self._setting_token(word)
        upper = word.upper()
        if not self._stmt_seen_token:
            self._stmt_seen_token = True
            self._stmt_is_copy = upper == "COPY"
        elif self._stmt_is_copy and self._prev_word == "FROM" and upper == "STDIN":
            self.copy_pending = True
        self._prev_word = upper

    def _mark_opaque_token_seen(self) -> None:
        self._stmt_seen_token = True
        self._prev_word = ""

    def _reset_statement(self) -> None:
        self._setting_state = 0
        self._word_limit = _COPY_WORD_MAX_LEN
        self._word = ""
        self._prev_word = ""
        self._stmt_seen_token = False
        self._stmt_is_copy = False

    @staticmethod
    def _get_command_word(line: str, pos: int, n: int) -> str:
        j = pos + 1
        if j < n and line[j] in "!.?\\":
            return line[pos : j + 1]
        k = j
        while k < n and line[k].isalpha():
            k += 1
        return line[pos:k] if k > j else line[pos : pos + 1]

    def _resume_block_comment(self, line: str, i: int, n: int) -> int:
        while i < n and self.comment_depth:
            if line[i] == "\n":
                self.lineno += 1
                i += 1
            elif line.startswith("/*", i):
                self.comment_depth += 1
                i += 2
            elif line.startswith("*/", i):
                self.comment_depth -= 1
                i += 2
            else:
                i += 1
        return i

    def _resume_dollar_body(self, line: str, i: int, n: int) -> int:
        tag = self.dollar_tag
        if tag is None:
            return i
        close = line.find(tag, i)
        if close == -1:
            self.lineno += line.count("\n", i)
            return n
        self.lineno += line.count("\n", i, close)
        self.dollar_tag = None
        return close + len(tag)

    def _resume_single_quote(self, line: str, i: int, n: int) -> int:
        capture = len(self._quoted_word) <= _SQL_WORD_MAX_LEN
        while i < n:
            ch = line[i]
            if capture and ch != "'":
                self._quoted_word += ch
                capture = len(self._quoted_word) <= _SQL_WORD_MAX_LEN
            if ch == "\n":
                self.lineno += 1
                i += 1
            elif ch == "\\" and self.single_quote_escaped:
                i += 2
            elif ch == "'":
                if i + 1 < n and line[i + 1] == "'":
                    i += 2
                else:
                    i += 1
                    self.in_single_quote = False
                    self._setting_token(self._quoted_word, quoted=True)
                    break
            else:
                i += 1
        return i

    def _resume_double_quote(self, line: str, i: int, n: int) -> int:
        capture = len(self._quoted_word) <= _SQL_WORD_MAX_LEN
        while i < n:
            if capture and line[i] != '"':
                self._quoted_word += line[i]
                capture = len(self._quoted_word) <= _SQL_WORD_MAX_LEN
            if line[i] == '"':
                if i + 1 < n and line[i + 1] == '"':
                    i += 2
                else:
                    i += 1
                    self.in_double_quote = False
                    self._setting_token(self._quoted_word, quoted=True)
                    break
            else:
                if line[i] == "\n":
                    self.lineno += 1
                i += 1
        return i


def _iter_physical_lines(text: str) -> Iterator[str]:
    start = 0
    while (idx := text.find("\n", start)) != -1:
        yield text[start : idx + 1]
        start = idx + 1
    if start < len(text):
        yield text[start:]


def _get_disallowed_psql_meta_command(text: str) -> tuple[int, str] | None:
    scanner = _PsqlSqlScanner()
    for line in _iter_physical_lines(text):
        hit = scanner.feed(line)
        if hit is not None:
            return hit
    return None


_CLUSTER_BOUND_STATEMENT_RE = re.compile(
    r"(?:CREATE USER MAPPING|GRANT|REVOKE|ALTER DEFAULT PRIVILEGES) "
)

_SQL_IDENT = r'(?:"(?:[^"]|"")*"|[^\s".;(),]+)'
_TARGET_SCHEMA_RE = re.compile(
    rf"(?:CREATE SCHEMA ({_SQL_IDENT});\s*$|COMMENT ON SCHEMA ({_SQL_IDENT}) IS )"
)
_TARGET_EXTENSION_COMMENT_RE = re.compile(rf"COMMENT ON EXTENSION ({_SQL_IDENT}) IS ")
_TARGET_UNUSED_SETVAL_RE = re.compile(
    r"SELECT pg_catalog\.setval\('((?:[^']|'')+)', 1, false\);\s*$"
)
_COPY_HEADER_RE = re.compile(rf"COPY ({_SQL_IDENT})\.({_SQL_IDENT}) .*FROM stdin;\s*$")
_QUALIFIED_RE = re.compile(rf"({_SQL_IDENT})\.({_SQL_IDENT})")


def _unquote(ident: str) -> str:
    if ident.startswith('"'):
        return ident[1:-1].replace('""', '"')
    return ident


@dataclass(frozen=True, slots=True)
class _RestoreTarget:
    schemas: frozenset[str]
    extensions: frozenset[str]
    extension_relations: frozenset[tuple[str, str]]

    @classmethod
    def read(cls, cr: BaseCursor) -> _RestoreTarget:
        cr.execute("SELECT nspname FROM pg_namespace")
        schemas = frozenset(row[0] for row in cr.fetchall())
        cr.execute("SELECT extname FROM pg_extension")
        extensions = frozenset(row[0] for row in cr.fetchall())
        cr.execute(
            "SELECT n.nspname, c.relname FROM pg_depend d"
            " JOIN pg_class c ON c.oid = d.objid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE d.classid = 'pg_class'::regclass"
            " AND d.refclassid = 'pg_extension'::regclass AND d.deptype = 'e'"
        )
        relations = frozenset((row[0], row[1]) for row in cr.fetchall())
        _debug.logic(
            "database.restore_target.read",
            schemas=len(schemas),
            extensions=len(extensions),
            extension_relations=len(relations),
        )
        return cls(schemas, extensions, relations)

    def get_drop_reason(self, text: str) -> str | None:
        if match := _TARGET_SCHEMA_RE.match(text):
            if _unquote(match.group(1) or match.group(2)) in self.schemas:
                return "schema the target holds"
        elif match := _TARGET_EXTENSION_COMMENT_RE.match(text):
            if _unquote(match.group(1)) in self.extensions:
                return "comment on an extension the target holds"
        elif match := _TARGET_UNUSED_SETVAL_RE.match(text):
            qualified = _QUALIFIED_RE.fullmatch(match.group(1).replace("''", "'"))
            if qualified is not None and self._holds_relation(*qualified.groups()):
                return "unused sequence of an extension the target holds"
        return None

    def holds_copy_target(self, text: str) -> bool:
        match = _COPY_HEADER_RE.match(text)
        return match is not None and self._holds_relation(*match.groups())

    def _holds_relation(self, schema: str, relation: str) -> bool:
        return (_unquote(schema), _unquote(relation)) in self.extension_relations


def _prepare_dump_command_error(hit: tuple[int, str]) -> RuntimeError:
    lineno, command = hit
    if not command.startswith("\\"):
        return RuntimeError(
            f"Refusing to restore: the dump's SQL sets {command!r} (line "
            f"{lineno}), which changes how a quoted string is escaped and "
            f"can desynchronize this scanner from what psql actually runs. "
            f"A backup produced by Odoo's own dump never needs this setting."
        )
    return RuntimeError(
        f"Refusing to restore: the dump's SQL contains the psql "
        f"meta-command {command!r} (line {lineno}), which would run with "
        f"this server's OS/database privileges. A backup produced by Odoo's "
        f"own dump contains no such command; the only permitted forms are "
        f"``\\restrict <key>`` / ``\\unrestrict <key>`` with an alphanumeric "
        f"key, and the ``\\.`` COPY terminator alone on its line."
    )


class _PortableSqlWriter:
    __slots__ = (
        "_buf",
        "_dropping",
        "_held_copy",
        "_in_overlong_line",
        "_max_line",
        "_out",
        "_target",
        "dropped",
        "scanner",
    )

    def __init__(self, out: IO[bytes], target: _RestoreTarget | None = None) -> None:
        self._out = out
        self._target = target
        self._held_copy: bytes | None = None
        self._max_line = get_env_int(
            "ODOO_DUMP_SCAN_MAX_LINE",
            _DEFAULT_MAX_SCAN_LINE,
            minimum=_MIN_MAX_SCAN_LINE,
            logger=_logger,
        )
        self._buf = bytearray()
        self._dropping = False
        self._in_overlong_line = False
        self.dropped = 0
        self.scanner = _PsqlSqlScanner()

    def write(self, data: bytes) -> int:
        buf = self._buf
        search = len(buf)
        buf += data
        start = 0
        while (nl := buf.find(b"\n", search)) != -1:
            self._take_line(bytes(buf[start : nl + 1]))
            start = search = nl + 1
        del buf[:start]
        if len(buf) > self._max_line:
            self._take_overlong_part(bytes(buf))
            buf.clear()
        return len(data)

    def finish(self) -> None:
        if self._buf:
            self._take_line(bytes(self._buf))
            self._buf.clear()
        if self._held_copy is not None:
            self._out.write(self._held_copy)
            self._held_copy = None
        _debug.logic(
            "database.dump_sql.filtered",
            lines=self.scanner.lineno,
            dropped=self.dropped,
            max_line=self._max_line,
        )

    def _take_overlong_part(self, part: bytes) -> None:
        if not (self._in_overlong_line or self.scanner.in_copy_data):
            _debug.logic(
                "database.dump_sql.line_too_long",
                lineno=self.scanner.lineno,
                max_line=self._max_line,
            )
            raise RuntimeError(
                f"Refusing to restore: the dump's SQL has a line longer than "
                f"{self._max_line} characters (at line {self.scanner.lineno}), "
                f"which cannot be scanned within a bounded amount of memory. A "
                f"backup produced by Odoo's own dump has no such line; raise "
                f"ODOO_DUMP_SCAN_MAX_LINE if this dump is genuinely legitimate."
            )
        if self._held_copy is not None:
            self._out.write(self._held_copy)
            self._held_copy = None
        if not self._in_overlong_line:
            _debug.logic(
                "database.dump_sql.copy_line_passed",
                lineno=self.scanner.lineno,
                max_line=self._max_line,
            )
            self._in_overlong_line = True
        self._out.write(part)

    def _take_line(self, line: bytes) -> None:
        scanner = self.scanner
        if self._in_overlong_line:
            self._in_overlong_line = False
            scanner.lineno += 1
            self._out.write(line)
            return
        text = line.decode("latin-1")
        if self._held_copy is not None:
            self._release_held_copy(line, text)
            return
        target = self._target
        hold_copy = False
        if not self._dropping and scanner.at_statement_start():
            reason = self._get_drop_reason(text)
            if reason is not None:
                _debug.logic(
                    "database.dump_sql.statement_dropped",
                    lineno=scanner.lineno,
                    reason=reason,
                )
                self._dropping = True
                self.dropped += 1
            elif target is not None and target.holds_copy_target(text):
                hold_copy = True
        self._feed(text)
        if hold_copy:
            self._held_copy = line
        elif not self._dropping:
            self._out.write(line)
        elif scanner.at_statement_start():
            self._dropping = False

    def _feed(self, text: str) -> None:
        hit = self.scanner.feed(text)
        if hit is not None:
            raise _prepare_dump_command_error(hit)

    def _get_drop_reason(self, text: str) -> str | None:
        if match := _CLUSTER_BOUND_STATEMENT_RE.match(text):
            return match.group(0).rstrip()
        if self._target is not None:
            return self._target.get_drop_reason(text)
        return None

    def _release_held_copy(self, line: bytes, text: str) -> None:
        held = self._held_copy
        assert held is not None
        self._held_copy = None
        self._feed(text)
        if not self.scanner.in_copy_data:
            _debug.logic(
                "database.dump_sql.statement_dropped",
                lineno=self.scanner.lineno,
                reason="empty copy into a table an extension of the target holds",
            )
            self.dropped += 1
            return
        self._out.write(held)
        self._out.write(line)


def copy_portable_sql(
    src: SupportsRead[bytes], dst: IO[bytes], target_db: str | None = None
) -> int:
    target = None
    if target_db is not None:
        with odoo.db.db_connect(target_db).cursor() as cr:
            target = _RestoreTarget.read(cr)
    writer = _PortableSqlWriter(dst, target)
    shutil.copyfileobj(src, writer)
    writer.finish()
    return writer.dropped


__all__ = (
    "_PortableSqlWriter",
    "_PsqlSqlScanner",
    "_RestoreTarget",
    "_get_disallowed_psql_meta_command",
    "_iter_physical_lines",
    "copy_portable_sql",
)
