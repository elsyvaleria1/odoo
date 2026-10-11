import functools
import re
from pathlib import Path

from odoo.modules import Manifest
from odoo.tools.misc import file_path

from . import _js_sources, lint_case

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_DO_ACTION = re.compile(r"(?<![\w$])doAction\(")
_OPTIONS_TYPEDEF = re.compile(
    r"@typedef \{Object\} ActionOptions\n(?P<body>(?: \* @property [^\n]*\n)+)"
)
_PROPERTY = re.compile(r"@property \{[^\n]*\} \[?([A-Za-z_$][\w$]*)")
_KEY = re.compile(r"\s*(?:\.\.\.|([A-Za-z_$][\w$]*|\"[^\"]*\"|'[^']*'))")


@functools.cache
def action_options() -> frozenset[str]:
    source = Path(
        file_path("web/static/src/webclient/actions/action_service.js")
    ).read_text(encoding="utf-8")
    body = _OPTIONS_TYPEDEF.search(source)["body"]
    return frozenset(_PROPERTY.findall(body))


def _balanced(code: str, start: int) -> int:
    # index of the bracket closing the one at `start`, strings skipped
    depth, quote, i = 0, None, start
    while i < len(code):
        char = code[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(code)


def _top_level_parts(code: str, start: int, end: int, separator: str) -> list[str]:
    parts, depth, quote, part_start, i = [], 0, None, start, start
    while i < end:
        char = code[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == separator and depth == 0:
            parts.append(code[part_start:i])
            part_start = i + 1
        i += 1
    parts.append(code[part_start:end])
    return parts


def unknown_options(source: str, known: frozenset[str]) -> list[tuple[int, str]]:
    code = _COMMENT.sub(lambda m: "\n" * m.group().count("\n"), source)
    found = []
    for call in _DO_ACTION.finditer(code):
        opening = call.end() - 1
        args = _top_level_parts(code, opening + 1, _balanced(code, opening), ",")
        if len(args) < 2 or not args[1].strip().startswith("{"):
            continue
        options = args[1].strip()
        for entry in _top_level_parts(options, 1, len(options) - 1, ","):
            key = _KEY.match(entry)
            name = key and key[1] and key[1].strip("\"'")
            if name and name not in known:
                found.append((code.count("\n", 0, call.start()) + 1, name))
    return found


@functools.cache
def _findings() -> dict[str, tuple[str, ...]]:
    known = action_options()
    repo_by_addon = {
        manifest.name: lint_case.repo_of(manifest.path)
        for manifest in Manifest.get_all_addon_manifests()
    }
    found: dict[str, list[str]] = {}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if not _js_sources.vendored(path):
            found.setdefault(repo_by_addon[addon], []).extend(
                f"{path}:{line} {name}" for line, name in unknown_options(source, known)
            )
    return {repo: tuple(items) for repo, items in sorted(found.items())}


class TestActionOptions(lint_case.LintCase):
    def test_no_unknown_do_action_option(self):
        self.assert_ratchet_per_repository(
            _findings(),
            "action_unknown_option",
            "doAction options the action service does not read in <repo>",
            "The action service reads only the keys ActionOptions declares "
            "(web/static/src/webclient/actions/action_service.js) and ignores "
            "any other without a word: spell the key it declares, or put what "
            "the action itself carries (its target, its params) on the action",
        )


class TestActionOptionsSeeTheirFaults(lint_case.LintCase):
    def test_the_declared_options_are_read_from_the_typedef(self):
        known = action_options()
        self.assertIn("clearBreadcrumbs", known)
        self.assertIn("stackPosition", known)
        self.assertNotIn("clear_breadcrumbs", known)

    def test_an_unknown_key_is_found_and_a_declared_one_is_not(self):
        source = (
            "this.action.doAction(action, { clear_breadcrumbs: true });\n"
            "// this.action.doAction(action, { nope: 1 });\n"
            "action.doAction('x', {\n"
            "    clearBreadcrumbs: true,\n"
            "    ...extra,\n"
            "    onClose: () => f({ target: 1 }),\n"
            "});\n"
            "action.doAction({ target: 'new' });\n"
            "action.doAction(request, options);\n"
            "doAction(request, { fullscreen: true });\n"
            "async doAction(request, options = {}) {}\n"
            "redoAction(request, { nope: 1 });\n"
        )
        known = frozenset({"clearBreadcrumbs", "onClose"})
        self.assertEqual(
            unknown_options(source, known),
            [(1, "clear_breadcrumbs"), (10, "fullscreen")],
        )
