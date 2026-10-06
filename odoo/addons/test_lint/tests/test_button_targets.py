import ast
import logging
import re
from pathlib import Path

from lxml import etree

from odoo.tests import tagged

from . import _parallel
from .lint_case import LintCase, _module_roots, is_core_path

_logger = logging.getLogger(__name__)

ACTION_NAME = re.compile(r"^action_\w+$")

DISPATCHING_TAGS = frozenset({"button", "a"})

JS_DISPATCH = (
    re.compile(r"""orm\.call\(\s*["'][\w.]+["']\s*,\s*["'](action_\w+)["']"""),
    re.compile(
        r"""doActionButton\s*\(\s*\{[^}]*?\bname:\s*["'](action_\w+)["']""",
        re.DOTALL,
    ),
)

_PARSER = etree.XMLParser(remove_comments=True, strip_cdata=False)

DEFINED_OUT_OF_SCOPE = frozenset(
    {
        "action_validate_mandate",
        "action_update_rights",
        "action_edit_dashboard",
    }
)

KNOWN_DANGLING = frozenset(
    {
        "action_trigger_technical_analysis",
        "action_invalidate_check",
        "action_set_quantities_to_reservation",
    }
)

EXEMPT = DEFINED_OUT_OF_SCOPE | KNOWN_DANGLING

type Dispatch = tuple[Path, int, str, str]


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return None


def _scan_python(entry: tuple[Path, bool]) -> tuple[set[str], list[Dispatch]]:
    # the methods a file defines, anywhere on the path, and the action_*
    # calls it makes, judged in this checkout only
    path, core = entry
    source = _read(path)
    if source is None:
        return set(), []
    defined = set(re.findall(r"\bdef ([A-Za-z_]\w*)", source))
    if not core or "action_" not in source:
        return defined, []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return defined, []
    return defined, [
        (path, node.lineno, node.func.attr, "call")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and ACTION_NAME.match(node.func.attr)
    ]


@tagged("post_install", "-at_install")
class ButtonTargetLinter(LintCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.defined = set()
        cls.dispatches = []
        python = []
        for root in _module_roots():
            core = is_core_path(root)
            for path in Path(root).rglob("*"):
                if "__pycache__" in path.parts:
                    continue
                if path.suffix == ".py":
                    python.append((path, core))
                elif core and path.suffix == ".xml":
                    cls._scan_xml(path, core)
                elif core and path.suffix == ".js":
                    cls._scan_js(path, core)
        for defined, dispatches in _parallel.map_items(_scan_python, python).values():
            cls.defined |= defined
            cls.dispatches.extend(dispatches)
        _logger.info(
            "%s method definitions, %s dispatch sites",
            len(cls.defined),
            len(cls.dispatches),
        )

    @classmethod
    def _scan_xml(cls, path, core):
        if not core:
            return
        try:
            tree = etree.parse(str(path), _PARSER)
        except etree.XMLSyntaxError, OSError:
            return
        for element in tree.iter():
            name = element.get("name")
            if (
                element.tag in DISPATCHING_TAGS
                and element.get("type") == "object"
                and name
                and ACTION_NAME.match(name)
            ):
                cls.dispatches.append((path, element.sourceline, name, "button"))
            elif element.tag == "field" and name == "python_method":
                target = (element.text or "").strip()
                if ACTION_NAME.match(target):
                    cls.dispatches.append(
                        (path, element.sourceline, target, "python_method"),
                    )

    @classmethod
    def _scan_js(cls, path, core):
        source = _read(path)
        if not core or source is None or "action_" not in source:
            return
        for pattern in JS_DISPATCH:
            for match in pattern.finditer(source):
                line = source.count("\n", 0, match.start()) + 1
                cls.dispatches.append((path, line, match.group(1), "js"))

    def test_known_dangling_entries_are_still_dangling(self):
        paid = sorted(KNOWN_DANGLING & self.defined)
        self.assertFalse(
            paid,
            f"{len(paid)} name(s) in KNOWN_DANGLING now resolve to a real method: "
            + ", ".join(paid)
            + ". The debt is paid -- delete them from the set so the gate goes back "
            "to enforcing them.",
        )

    def test_dispatched_names_exist(self):
        self.assertTrue(self.dispatches, "the scan found no dispatch sites at all")
        offenders = [
            f"{path}:{line} ({kind}) {name}"
            for path, line, name, kind in self.dispatches
            if name not in self.defined and name not in EXEMPT
        ]
        self.assert_ratchet(
            sorted(offenders),
            "lint_dispatch_target",
            "dispatch(es) naming a method that is defined nowhere in the tree",
            "Rename the caller with the method, or restore the method. Only the XML "
            "ones fail at install; a Python or JS dispatch fails when a user presses "
            "the button.",
        )
        dispatched = {name for _, _, name, _ in self.dispatches}
        if unused := sorted(EXEMPT - dispatched):
            _logger.info(
                "%s exemption(s) not in scope on this addons path -- no dispatch "
                "reaches them here, so this run neither enforces nor clears them. "
                "A wide run reporting the same names means the caller is gone and "
                "the entry can be deleted: %s",
                len(unused),
                ", ".join(unused),
            )
