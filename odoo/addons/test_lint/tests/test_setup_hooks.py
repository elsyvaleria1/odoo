import functools
import re
from collections import defaultdict
from pathlib import Path

from odoo.modules import Manifest
from odoo.tests.common import BaseCase, no_retry

from . import lint_case

SIGNALS = {
    "modality": re.compile(r"\b(?:isTouch|inputModality)\b"),
    "viewport": re.compile(r"\bisSmall\b|\bui\.size\b"),
}

HOOK_CALL_RE = re.compile(r"\buse[A-Z]\w*\s*\(")
SETUP_RE = re.compile(r"(?m)^[ \t]*(?:async\s+)?setup\s*\(\s*\)\s*\{")
GETTER_RE = re.compile(r"(?m)^[ \t]*get\s+(\w+)\s*\(\s*\)\s*\{")
IF_RE = re.compile(r"\bif\s*\(")
ELSE_RE = re.compile(r"\s*else\b")
THIS_MEMBER_RE = re.compile(r"\bthis\.(\w+)\b")

_LITERAL_OR_COMMENT_RE = re.compile(
    r"""//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|`(?:\\.|[^`\\])*`""",
    re.DOTALL,
)

_SKIPPED_PARTS = frozenset({"tests", "lib", "o_spreadsheet"})


def _mask(source: str) -> str:
    return _LITERAL_OR_COMMENT_RE.sub(
        lambda match: re.sub(r"[^\n]", " ", match.group(0)), source
    )


def _closing(code: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    for index in range(start, len(code)):
        if code[index] == opening:
            depth += 1
        elif code[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return len(code) - 1


def _branch(code: str, start: int) -> tuple[str, int]:
    index = start
    while index < len(code) and code[index].isspace():
        index += 1
    if index < len(code) and code[index] == "{":
        end = _closing(code, index, "{", "}")
        return code[index : end + 1], end + 1
    end = code.find(";", index)
    end = len(code) if end < 0 else end + 1
    return code[index:end], end


def _signal_getters(code: str) -> dict[str, set[str]]:
    bodies = {}
    for match in GETTER_RE.finditer(code):
        brace = match.end() - 1
        bodies[match.group(1)] = code[brace : _closing(code, brace, "{", "}") + 1]
    reading = {kind: set() for kind in SIGNALS}
    changed = True
    while changed:
        changed = False
        for name, body in bodies.items():
            for kind, signal in SIGNALS.items():
                if name in reading[kind]:
                    continue
                members = set(THIS_MEMBER_RE.findall(body))
                if signal.search(body) or members & reading[kind]:
                    reading[kind].add(name)
                    changed = True
    return reading


def conditional_setup_hooks(source: str) -> dict[str, list[int]]:
    code = _mask(source)
    getters = _signal_getters(code)
    found = {kind: [] for kind in SIGNALS}
    for setup in SETUP_RE.finditer(code):
        brace = setup.end() - 1
        body_end = _closing(code, brace, "{", "}")
        position = brace + 1
        while (match := IF_RE.search(code, position, body_end)) is not None:
            paren = match.end() - 1
            condition_end = _closing(code, paren, "(", ")")
            condition = code[paren : condition_end + 1]
            branches, after = _branch(code, condition_end + 1)
            if other := ELSE_RE.match(code, after):
                otherwise, _after = _branch(code, other.end())
                branches += otherwise
            if HOOK_CALL_RE.search(branches):
                members = set(THIS_MEMBER_RE.findall(condition))
                line = code.count("\n", 0, match.start()) + 1
                for kind, signal in SIGNALS.items():
                    if signal.search(condition) or members & getters[kind]:
                        found[kind].append(line)
            position = match.end()
    return found


@functools.cache
def _findings() -> dict[str, dict[str, list[str]]]:
    findings = {kind: defaultdict(list) for kind in SIGNALS}
    for manifest in Manifest.get_all_addon_manifests():
        static = Path(manifest.path) / "static"
        if manifest.name.startswith("test_") or not static.is_dir():
            continue
        repo = lint_case.repo_of(str(manifest.path))
        for path in sorted(static.rglob("*.js")):
            if _SKIPPED_PARTS.intersection(path.relative_to(static).parts):
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except OSError, UnicodeDecodeError:
                continue
            if "setup" not in source:
                continue
            relative = path.relative_to(Path(manifest.path).parent)
            for kind, lines in conditional_setup_hooks(source).items():
                findings[kind][repo].extend(f"{relative}:{line}" for line in lines)
    return findings


class TestSetupHooks(lint_case.LintCase):
    def test_no_hook_waits_on_the_input_modality(self):
        found = _findings()["modality"]
        self.assert_ratchet_per_repository(
            found,
            "setup_hook_modality",
            "hook(s) installed in setup() under an input-modality condition in <repo>",
            "The modality changes with every pointer, so setup() "
            "freezes whatever it was at mount. Install the hook "
            "unconditionally and decide when it acts: a draggable's "
            "enable: () => …, or a check inside its handler.",
        )

    def test_no_hook_waits_on_the_viewport_size(self):
        found = _findings()["viewport"]
        self.assert_ratchet_per_repository(
            found,
            "setup_hook_viewport",
            "hook(s) installed in setup() under a viewport-size condition in <repo>",
            "setup() freezes the width the component mounted at; a "
            "resize never installs or removes the hook. Install it "
            "unconditionally and read ui.isSmall when it acts.",
        )


@no_retry
class TestSetupHookScan(BaseCase):
    def test_a_hook_under_a_signal_in_setup_is_found(self):
        source = (
            "class A extends Component {\n"
            "    setup() {\n"
            "        this.ui = useService('ui');\n"
            "        if (this.ui.isTouch) {\n"
            "            useSwipe();\n"
            "        }\n"
            "        if (this.env.isSmall) useFoldable();\n"
            "        if (this.canDrag) {\n"
            "            useDraggable({});\n"
            "        } else {\n"
            "            useNothing();\n"
            "        }\n"
            "    }\n"
            "    get canDrag() {\n"
            "        return this.isEditable && !this.ui.isSmall;\n"
            "    }\n"
            "    get isEditable() {\n"
            "        return inputModality.current === 'mouse';\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(
            conditional_setup_hooks(source),
            {"modality": [4, 8], "viewport": [7, 8]},
        )

    def test_a_decision_taken_when_the_hook_acts_is_clean(self):
        source = (
            "class A extends Component {\n"
            "    setup() {\n"
            "        useDraggable({ enable: () => !this.ui.isSmall });\n"
            "        if (this.ui.isTouch) {\n"
            "            this.state.compact = true;\n"
            "        }\n"
            "        // if (this.ui.isSmall) { useFoldable(); }\n"
            "        const label = 'if (ui.isSmall) { useX(); }';\n"
            "    }\n"
            "    onClick() {\n"
            "        if (this.ui.isSmall) {\n"
            "            useLater();\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(
            conditional_setup_hooks(source), {"modality": [], "viewport": []}
        )
