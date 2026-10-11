import bisect
import functools
import re
from pathlib import Path

from odoo.modules import Manifest
from odoo.tests.common import BaseCase, no_retry

from . import _js_sources, lint_case

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_OWN_RENDER = re.compile(r"^\s+render\s*\([^)]*\)\s*\{", re.MULTILINE)
_XML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SUB_ENV = re.compile(r"(?<![\w.$])use(?:Child)?SubEnv\s*\(")
_PROPS_WRITE = re.compile(
    r"(?<![\w.$])[A-Z]\w*\.(?:props|defaultProps)\s*=(?!=)"
    r"|\bObject\.assign\(\s*[A-Z]\w*\.(?:props|defaultProps)\b"
)
_PATCH_CLASS = re.compile(r"(?<![\w.$])patch\(\s*[A-Z]\w*\s*,\s*\{")
_OBJECT_EXTENSION = re.compile(r"(?<![\w.$])Object\.assign\(\s*([A-Za-z_$][\w$]*)\s*,")
_EXPORTED_OBJECT = re.compile(
    r"^export\s+const\s+([A-Za-z_$][\w$]*)\s*=\s*\{", re.MULTILINE
)
_STATIC_PROPS = re.compile(r"\bstatic\s+props\s*=\s*\{")
_PROPS_KEY = re.compile(r"(?<![\w$])(?:props|defaultProps)\s*:")
_USE_ENV = re.compile(r"(?<![\w.$])useEnv\s*\(")
_STRING_OR_COMMENT = re.compile(
    r"(\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`)"
    r"|/\*.*?\*/|//[^\n]*",
    re.DOTALL,
)
_COMPONENT_CLASS = re.compile(r"\bclass\s+[A-Za-z_$][\w$]*\s+extends\s+Component\s*\{")
_PROPS_READ = re.compile(r"\bthis\.props\b")
_PROPS_FIELD = re.compile(r"^\s*props\s*=(?!=)", re.MULTILINE)
_ACCESSOR = re.compile(
    r"^(?:export\s+)?function\s+(?:use|provide)[A-Z]\w*\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_SINGLE_RETURN = re.compile(r"\{\s*return\b[^;{}]*;\s*\}", re.DOTALL)
_PROVIDER = re.compile(
    r"^(?:export\s+)?function\s+provide[A-Z]\w*\s*\([^)]*\)\s*\{", re.MULTILINE
)
_USE_LISTENER = re.compile(r"(?<![\w.$])useListener\s*\(")
_REF_READ = re.compile(r"\.el\b")
_FUNCTION_DEF = re.compile(
    r"^[ \t]*(?:export\s+)?(?:async\s+)?(?:function\s+)?([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{",
    re.MULTILINE,
)
_VALUE_DEF = re.compile(
    r"^[ \t]*(?:export\s+)?(?:(?:const|let|var)\s+)?([A-Za-z_$][\w$]*)\s*=(?![=>])",
    re.MULTILINE,
)
_NAME_USE = re.compile(
    r"(?:(?<=\.)(?=[A-Za-z_$][\w$]*\s*\()|(?<=this\.)|(?<![\w.$]))([A-Za-z_$][\w$]*)"
)
_NOT_A_DEFINITION = frozenset(
    {"if", "for", "while", "switch", "catch", "function", "return", "with"}
)
_CALLEE_DEPTH = 4
ENV_KEYS = {
    "owl_env_reads": re.compile(r"\bthis\.env\b"),
    "owl_env_dialog_context": re.compile(
        r"\bthis\.env\.(?:inDialog|dialogId|dialogData)\b"
    ),
    "owl_env_is_small": re.compile(r"\bthis\.env\.isSmall\b"),
    "owl_env_model": re.compile(r"\bthis\.env\.model\b"),
    "owl_env_mail_context": re.compile(
        r"\bthis\.env\.(?:"
        r"inChatter|inChatWindow|inChatBubble|inComposer|"
        r"inDiscussActionPanel|inDiscussApp|inDiscussCallView|"
        r"inDiscussSidebar|inLivechatInfoPanel|inMeetingChat|"
        r"inMeetingSideActions|inMeetingView|inMessage|"
        r"inMessagingMenu|inNotificationItem|inWelcomePage|"
        r"inCallDropdown|inCallInvitation|inCallMenu|"
        r"isDiscussPipBanner|inFrontendPortalChatter|alignedRight|"
        r"chatter|closeActionPanel|embedLivechat|filteredThreads|"
        r"fullComposerBus|getCurrentThread|message|messageCard|"
        r"messageHighlight|messageSearch|onImageLoaded|pinMenu|"
        r"searchMenu|subChannelMenu|threadHeights|pipWindow"
        r")\b"
    ),
    "owl_env_builder_context": re.compile(
        r"\bthis\.env\.(?:editor|editorBus|triggerDomUpdated|editColorCombination|"
        r"dependencyManager|getEditingElements?|weContext|selectableContext|imgGroup|"
        r"ignoreBuilderItem|onSelectItem|colorPresetToShow)\b"
    ),
    "owl_env_addon_contexts": re.compile(
        r"\bthis\.env\.(?:overlayState|localOverlayContainerKey|controller|component|"
        r"template|modelStore|calendarState|timeOffBus|searchState|onClickViewButton|"
        r"orderResModel|orderId|productId|currencyId|digits|displayUoM|precision|"
        r"childField|increaseQuantity|decreaseQuantity|addProduct|removeProduct|"
        r"setQuantity|mainProductTmplId|currency|canChangeVariant|showQuantity|"
        r"showPackaging|showPrice|setUoM|updateProductTemplateSelectedPTAV|"
        r"updatePTAVCustomValue|isPossibleCombination|__beforeLeave__|"
        r"__getGlobalState__|__getLocalState__|__getContext__|__getOrderBy__|"
        r"resUserGroupsInfo|searchPanelState|showAllContainer|companySelector|addPage|"
        r"getCssLinkEls|setPopout|dashboardState|setDragging|removeRecord|selectedValues|"
        r"projectSharingId|shouldCollapse|approvalGatedModels|orderlineGroupOf|"
        r"stockDashboardAllSample|openRecord|isQuantityAllowed|productCatalogPendingUpdates|"
        r"isFrontend|isMainProductConfigurable|displayRating|reload)\b"
    ),
    "owl_env_bus": re.compile(r"\bthis\.env\.bus\b"),
    "owl_env_debug": re.compile(r"\bthis\.env\.debug\b"),
    "owl_env_config": re.compile(r"\bthis\.env\.config\b"),
    "owl_env_search_model": re.compile(r"\bthis\.env\.searchModel\b"),
    "owl_env_utils": re.compile(r"\bthis\.env\.utils\b"),
}
REMOVED_IN_OWL3 = {
    "owl_on_rendered": re.compile(r"(?<![\w.$])onRendered\s*\("),
    "owl_on_will_render": re.compile(r"(?<![\w.$])onWillRender\s*\("),
    "owl_this_render": re.compile(r"\bthis\.render\s*\("),
    "owl_use_component": re.compile(r"(?<![\w.$])useComponent\s*\("),
    "owl_use_effect": re.compile(r"(?<![\w.$])useEffect\s*\("),
    "owl_env_services": re.compile(r"\bthis\.env\.services\b"),
}


_OWL_IMPORT = re.compile(
    r"\bimport\s*\{([^}]*)\}\s*from\s*[\"']@odoo/owl[\"']", re.DOTALL
)
_OWL_EXPORT_BLOCK = re.compile(r"^export\s*\{([^}]*)\}", re.MULTILINE)


@functools.cache
def owl_exports() -> frozenset[str]:
    owl = Path(Manifest.for_addon("web").path) / "static" / "lib" / "owl" / "owl.es.js"
    blocks = _OWL_EXPORT_BLOCK.findall(owl.read_text(encoding="utf-8"))
    return frozenset(
        name.split(" as ")[-1].strip() for name in blocks[-1].split(",") if name.strip()
    )


def removed_owl_imports(source: str, exported: frozenset[str]) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    found = []
    for m in _OWL_IMPORT.finditer(code):
        offset = m.start(1)
        for name in re.finditer(
            r"[A-Za-z_$][\w$]*(?:\s+as\s+[A-Za-z_$][\w$]*)?", m.group(1)
        ):
            imported = name.group(0).split()[0]
            if imported not in exported:
                found.append(code.count("\n", 0, offset + name.start()) + 1)
    return found


def _strip_comments(source: str) -> str:
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)


def _lines_of(pattern: re.Pattern, code: str, newlines: list[int]) -> list[int]:
    return [
        bisect.bisect_right(newlines, m.start()) + 1 for m in pattern.finditer(code)
    ]


_GUARD = re.compile(r"^(?:\(\?<!\[[^\]]*\]\)|\\b)+")


def required_literal(pattern: re.Pattern) -> str:
    text = _GUARD.sub("", pattern.pattern)
    depth = 0
    for char in text.replace("\\(", "").replace("\\)", "").replace("\\|", ""):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "|" and not depth:
            return ""
    literal = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and text[index + 1 : index + 2] in tuple(".$(){}[]"):
            literal.append(text[index + 1])
            index += 2
        elif char.isalnum() or char == "_":
            literal.append(char)
            index += 1
        else:
            break
    return "".join(literal)


def _newlines(code: str) -> list[int]:
    return [m.start() for m in re.finditer(r"\n", code)]


def _code_calls(pattern: re.Pattern, code: str, newlines: list[int]) -> list[int]:
    if pattern is REMOVED_IN_OWL3["owl_this_render"] and _OWN_RENDER.search(code):
        return []
    return _lines_of(pattern, code, newlines)


def calls(pattern: re.Pattern, source: str) -> list[int]:
    code = _strip_comments(source)
    return _code_calls(pattern, code, _newlines(code))


def _body_end(code: str, open_brace: int) -> int:
    depth = 0
    for index in range(open_brace, len(code)):
        if code[index] == "{":
            depth += 1
        elif code[index] == "}":
            depth -= 1
            if not depth:
                return index
    return len(code)


def patched_props_calls(source: str) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    starts = [m.start() for m in _PROPS_WRITE.finditer(code)]
    for m in _PATCH_CLASS.finditer(code):
        body_start = m.end() - 1
        body_end = _body_end(code, body_start)
        depth = 0
        for index in range(body_start, body_end):
            char = code[index]
            if char in "{([":
                depth += 1
            elif char in "})]":
                depth -= 1
            elif depth == 1 and _PROPS_KEY.match(code, index):
                starts.append(index)
    return sorted(code.count("\n", 0, start) + 1 for start in starts)


def extended_objects(source: str) -> set[str]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    return set(_OBJECT_EXTENSION.findall(code))


def copied_props_calls(source: str, extended: set[str] | frozenset[str]) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    owned = set(_EXPORTED_OBJECT.findall(code)) & extended
    if not owned:
        return []
    spread = re.compile(r"\.\.\.\s*(?:%s)\b" % "|".join(map(re.escape, owned)))
    lines = []
    for m in _STATIC_PROPS.finditer(code):
        body_start = m.end() - 1
        if spread.search(code, body_start, _body_end(code, body_start)):
            lines.append(code.count("\n", 0, m.start()) + 1)
    return lines


def raw_use_env_calls(source: str) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    accessors = []
    for m in _ACCESSOR.finditer(code):
        end = _body_end(code, m.end() - 1)
        if _SINGLE_RETURN.fullmatch(code, m.end() - 1, end + 1):
            accessors.append((m.start(), end))
    return [
        code.count("\n", 0, m.start()) + 1
        for m in _USE_ENV.finditer(code)
        if not any(start <= m.start() < end for start, end in accessors)
    ]


def unbound_props_reads(source: str) -> list[int]:
    code = _STRING_OR_COMMENT.sub(
        lambda m: m.group(1) or "\n" * m.group(0).count("\n"), source
    )
    lines = []
    for m in _COMPONENT_CLASS.finditer(code):
        body = code[m.end() : _body_end(code, m.end() - 1)]
        if _PROPS_READ.search(body) and not _PROPS_FIELD.search(body):
            lines.append(code.count("\n", 0, m.start()) + 1)
    return lines


def raw_sub_env_calls(source: str) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    providers = [
        (m.start(), _body_end(code, m.end() - 1)) for m in _PROVIDER.finditer(code)
    ]
    return [
        code.count("\n", 0, m.start()) + 1
        for m in _SUB_ENV.finditer(code)
        if not any(start <= m.start() < end for start, end in providers)
    ]


def _skip_string(code: str, index: int) -> int:
    quote = code[index]
    index += 1
    while index < len(code) and code[index] != quote:
        index += 2 if code[index] == "\\" else 1
    return index


def _expression_end(code: str, start: int) -> int:
    depth = 0
    index = start
    while index < len(code):
        char = code[index]
        if char in "'\"`":
            index = _skip_string(code, index)
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return index
        elif char == ";" and not depth:
            return index
        index += 1
    return len(code)


def _call_arguments(code: str, open_paren: int) -> list[str]:
    arguments = []
    depth = 0
    start = open_paren + 1
    index = open_paren
    while index < len(code):
        char = code[index]
        if char in "'\"`":
            index = _skip_string(code, index)
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if not depth:
                arguments.append(code[start:index])
                return arguments
        elif char == "," and depth == 1:
            arguments.append(code[start:index])
            start = index + 1
        index += 1
    return arguments


def _definitions(code: str) -> dict[str, str]:
    bodies: dict[str, list[str]] = {}
    for m in _FUNCTION_DEF.finditer(code):
        if m.group(1) not in _NOT_A_DEFINITION:
            end = _body_end(code, m.end() - 1)
            bodies.setdefault(m.group(1), []).append(code[m.start() : end + 1])
    for m in _VALUE_DEF.finditer(code):
        end = _expression_end(code, m.end())
        bodies.setdefault(m.group(1), []).append(code[m.end() : end])
    return {name: "\n".join(parts) for name, parts in bodies.items()}


def setup_listener_ref_reads(source: str) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)
    definitions = None
    lines = []
    for m in _USE_LISTENER.finditer(code):
        arguments = _call_arguments(code, m.end() - 1)
        if len(arguments) < 3:
            continue
        if definitions is None:
            definitions = _definitions(code)
        reached = arguments[2]
        frontier = [reached]
        seen: set[str] = set()
        for _ in range(_CALLEE_DEPTH):
            names = {n for text in frontier for n in _NAME_USE.findall(text)}
            fresh = sorted((names & definitions.keys()) - seen)
            seen.update(fresh)
            frontier = [definitions[name] for name in fresh]
            reached += "\n".join(["", *frontier])
        if _REF_READ.search(reached):
            lines.append(code.count("\n", 0, m.start()) + 1)
    return lines


def _strip_xml_comments(source: str) -> str:
    return _XML_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), source)


def template_calls(pattern: re.Pattern, source: str) -> list[int]:
    code = _strip_xml_comments(source)
    return _lines_of(pattern, code, _newlines(code))


@functools.cache
def _repo_by_addon() -> dict[str, str]:
    return {
        manifest.name: lint_case.repo_of(manifest.path)
        for manifest in Manifest.get_all_addon_manifests()
    }


@functools.cache
def _gate_findings() -> dict[str, dict[str, tuple[str, ...]]]:
    gates = {**REMOVED_IN_OWL3, **ENV_KEYS}
    literals = {gate: required_literal(pattern) for gate, pattern in gates.items()}
    repo_by_addon = _repo_by_addon()
    repos = sorted(set(repo_by_addon.values()))
    found = {gate: {repo: [] for repo in repos} for gate in gates}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if "/static/src/" not in path.as_posix() or _js_sources.vendored(path):
            continue
        code = _strip_comments(source)
        newlines = None
        for gate, pattern in gates.items():
            if literals[gate] not in code or not pattern.search(code):
                continue
            newlines = newlines if newlines is not None else _newlines(code)
            found[gate][repo_by_addon[addon]] += [
                f"{path}:{line}" for line in _code_calls(pattern, code, newlines)
            ]
    for manifest in Manifest.get_all_addon_manifests():
        src = Path(manifest.path) / "static" / "src"
        if not src.is_dir():
            continue
        for path in sorted(src.rglob("*.xml")):
            if _js_sources.vendored(path):
                continue
            code = _strip_xml_comments(path.read_text(errors="replace"))
            newlines = None
            for gate, pattern in ENV_KEYS.items():
                if literals[gate] not in code or not pattern.search(code):
                    continue
                newlines = newlines if newlines is not None else _newlines(code)
                found[gate][repo_by_addon[manifest.name]] += [
                    f"{path}:{line}" for line in _lines_of(pattern, code, newlines)
                ]
    return {
        gate: {repo: tuple(items) for repo, items in by_repo.items()}
        for gate, by_repo in found.items()
    }


def _findings(gate: str) -> dict[str, tuple[str, ...]]:
    return _gate_findings()[gate]


_SCANNERS = {
    "owl_setup_listener_ref": setup_listener_ref_reads,
    "owl_sub_env_raw": raw_sub_env_calls,
    "owl_patched_props": patched_props_calls,
    "owl_use_env_raw": raw_use_env_calls,
}


@functools.cache
def _copied_props_findings() -> dict[str, tuple[str, ...]]:
    sources = [
        (addon, path, source)
        for addon, path, source in _js_sources.addon_js_outside_lib()
        if "/static/src/" in path.as_posix() and not _js_sources.vendored(path)
    ]
    extended = frozenset().union(*(extended_objects(src) for _a, _p, src in sources))
    repo_by_addon = _repo_by_addon()
    found: dict[str, list[str]] = {repo: [] for repo in repo_by_addon.values()}
    for addon, path, source in sources:
        found[repo_by_addon[addon]] += [
            f"{path}:{line}" for line in copied_props_calls(source, extended)
        ]
    return {repo: tuple(items) for repo, items in sorted(found.items())}


@functools.cache
def _scan_findings(gate: str) -> dict[str, tuple[str, ...]]:
    scan = _SCANNERS[gate]
    repo_by_addon = _repo_by_addon()
    found: dict[str, list[str]] = {repo: [] for repo in repo_by_addon.values()}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if "/static/src/" in path.as_posix() and not _js_sources.vendored(path):
            found[repo_by_addon[addon]] += [f"{path}:{line}" for line in scan(source)]
    return {repo: tuple(items) for repo, items in sorted(found.items())}


@functools.cache
def _unbound_props_findings() -> dict[str, tuple[str, ...]]:
    repo_by_addon = _repo_by_addon()
    found: dict[str, list[str]] = {repo: [] for repo in repo_by_addon.values()}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if not _js_sources.vendored(path):
            found[repo_by_addon[addon]] += [
                f"{path}:{line}" for line in unbound_props_reads(source)
            ]
    return {repo: tuple(items) for repo, items in sorted(found.items())}


@functools.cache
def _removed_import_findings() -> dict[str, tuple[str, ...]]:
    exported = owl_exports()
    repo_by_addon = _repo_by_addon()
    found: dict[str, list[str]] = {repo: [] for repo in repo_by_addon.values()}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if not _js_sources.vendored(path):
            found[repo_by_addon[addon]] += [
                f"{path}:{line}" for line in removed_owl_imports(source, exported)
            ]
    return {repo: tuple(items) for repo, items in sorted(found.items())}


class TestOwl3Api(lint_case.LintCase):
    def test_no_import_of_a_name_owl_no_longer_exports(self):
        self._assert_per_repo(
            _removed_import_findings(),
            "owl_removed_import",
            "imports from @odoo/owl of a name it does not export",
            "The import fails at link time, and with it every module of the bundle "
            "that reaches it: a whole web client, not one screen. OWL 3 dropped "
            "useState (proxy), useRef (elementRef from @web/core/utils/element_ref, "
            't-ref="this.x"), useExternalListener (useListener), useEnv, '
            "useSubEnv, useChildSubEnv, useComponent, onRendered, onWillRender, "
            "reactive (proxy) and validate.",
        )

    def _assert_gate(self, gate: str, what: str, fix: str) -> None:
        self._assert_per_repo(_findings(gate), gate, what, fix)

    def _assert_per_repo(
        self, found: dict[str, tuple[str, ...]], gate: str, what: str, fix: str
    ) -> None:
        self.assert_ratchet_per_repository(found, gate, f"{what} in <repo>", fix)

    def _assert_removed(self, gate: str, api: str, fix: str) -> None:
        self._assert_gate(gate, f"{api} calls (removed in OWL 3)", fix)

    def test_no_on_rendered(self):
        self._assert_removed(
            "owl_on_rendered",
            "onRendered",
            "Work that must follow a render reacts to the data instead: a value "
            "the render shows is a template binding or a useEffect on it, DOM "
            "work is onMounted/onPatched",
        )

    def test_no_on_will_render(self):
        self._assert_removed(
            "owl_on_will_render",
            "onWillRender",
            "Derive the value where it is read (a getter, or a useEffect keyed "
            "on its inputs); OWL 3 has no render hook",
        )

    def test_no_this_render(self):
        self._assert_removed(
            "owl_this_render",
            "this.render()",
            "Make the data the template reads reactive, so writing it re-renders; "
            "OWL 3 components have no render()",
        )

    def test_no_use_component(self):
        self._assert_removed(
            "owl_use_component",
            "useComponent()",
            "A hook takes what it needs as arguments or reads it through its "
            "own hooks; OWL 3 has no useComponent",
        )

    def test_no_use_effect(self):
        self._assert_removed(
            "owl_use_effect",
            "useEffect()",
            "Call useLayoutEffect from @web/core/utils/layout_effect, OWL 2's "
            "dependency-array effect built on onMounted / onPatched; OWL 3's "
            "useEffect takes no dependencies and re-runs on every reactive read",
        )

    def test_no_env_dialog_context(self):
        self._assert_gate(
            "owl_env_dialog_context",
            "this.env.inDialog / dialogId / dialogData reads in static/src (JS and templates)",
            "A component inside a dialog reads this.dialogContext = "
            "useDialogContext() (@web/core/dialog_context_hooks) from setup; "
            "OWL 3 components have no env",
        )

    def test_no_env_is_small(self):
        self._assert_gate(
            "owl_env_is_small",
            "this.env.isSmall reads in static/src (JS and templates)",
            'A component reads this.ui.isSmall from this.ui = useService("ui") '
            "in setup; OWL 3 components have no env",
        )

    def test_no_env_mail_context(self):
        self._assert_gate(
            "owl_env_mail_context",
            "this.env.<mail context key> reads in static/src (JS and templates)",
            "A mail component reads this.mailContext = useMailContext() from "
            "setup, and a mail scope provides its keys with provideMailContext / "
            "provideChildMailContext (@mail/utils/common/mail_context); OWL 3 "
            "components have no env",
        )

    def test_no_env_model(self):
        self._assert_gate(
            "owl_env_model",
            "this.env.model reads in static/src (JS and templates)",
            "A component under a view reads this.model = useViewModel() from "
            "setup, and a view provides it with provideViewModel(model); OWL 3 "
            "components have no env",
        )

    def test_no_env_builder_context(self):
        self._assert_gate(
            "owl_env_builder_context",
            "this.env.<builder context key> reads in static/src (JS and templates)",
            "A builder component reads this.builderContext = useBuilderContext() "
            "from setup, and a builder scope provides its keys with "
            "provideBuilderContext (@html_builder/core/builder_context); OWL 3 "
            "components have no env",
        )

    def test_no_env_addon_contexts(self):
        self._assert_gate(
            "owl_env_addon_contexts",
            "this.env reads of an addon-scoped context key in static/src (JS and templates)",
            "A component reads the context its addon scopes through that addon's "
            "grouped accessor (useEditorOverlayContext, useAccountReportContext, "
            "useDocModelStore, useAppointmentCalendarContext, useTimeOffContext, "
            "useSettingsSearchContext, useViewButtonContext, useProductCatalogContext, "
            "useProductConfiguratorContext); OWL 3 components have no env",
        )

    def test_no_env_bus(self):
        self._assert_gate(
            "owl_env_bus",
            "this.env.bus reads in static/src (JS and templates)",
            "A component reads this.bus = useEventBus() from setup, and a "
            "component that scopes a bus of its own provides it with "
            "provideEventBus (both in @web/core/utils/hooks); OWL 3 components "
            "have no env",
        )

    def test_no_env_debug(self):
        self._assert_gate(
            "owl_env_debug",
            "this.env.debug reads in static/src (JS and templates)",
            "A component reads this.debug = useDebugMode() "
            "(@web/core/debug/debug_context) from setup; OWL 3 components have "
            "no env",
        )

    def test_no_env_config(self):
        self._assert_gate(
            "owl_env_config",
            "this.env.config reads in static/src (JS and templates)",
            "A component reads this.config = useViewConfig() from setup, and a "
            "view, action or dialog provides it with provideViewConfig (both in "
            "@web/core/view_config_hooks); OWL 3 components have no env",
        )

    def test_no_env_search_model(self):
        self._assert_gate(
            "owl_env_search_model",
            "this.env.searchModel reads in static/src (JS and templates)",
            "A component under WithSearch reads this.searchModel = "
            "useSearchModel() from setup, and WithSearch provides it with "
            "provideSearchModel; OWL 3 components have no env",
        )

    def test_no_env_utils(self):
        self._assert_gate(
            "owl_env_utils",
            "this.env.utils reads in static/src (JS and templates)",
            "A point_of_sale component reads this.utils = "
            'useService("contextual_utils_service") from setup; OWL 3 '
            "components have no env",
        )

    def test_no_env_reads(self):
        self._assert_gate(
            "owl_env_reads",
            "this.env reads in static/src, components or not (JS and templates)",
            "A component reads what its env carried through the accessor of the "
            "scope that provides it; a service, store or model that keeps an env of "
            "its own reads it until that owner is given one. OWL 3 has no env",
        )

    def test_no_env_services(self):
        self._assert_removed(
            "owl_env_services",
            "this.env.services",
            "A component takes its service in setup with useService / "
            "useOptionalService; OWL 3 components have no env",
        )

    def test_no_raw_sub_env(self):
        self._assert_per_repo(
            _scan_findings("owl_sub_env_raw"),
            "owl_sub_env_raw",
            "useSubEnv / useChildSubEnv calls outside a provide* function",
            "A scope hands a value to its descendants through the provide* hook "
            "paired with the use* accessor its readers call; OWL 3 has no env, so "
            "each pair becomes a plugin",
        )

    def test_no_raw_use_env(self):
        self._assert_per_repo(
            _scan_findings("owl_use_env_raw"),
            "owl_use_env_raw",
            "useEnv() calls outside a use* / provide* accessor that only returns it",
            "A hook reads what its scope provides through that scope's accessor "
            "(useServices, useEventBus, useBuilderContext, ...); OWL 3 has no env, "
            "so each accessor becomes a plugin read",
        )

    def test_no_setup_listener_reading_a_ref(self):
        self._assert_per_repo(
            _scan_findings("owl_setup_listener_ref"),
            "owl_setup_listener_ref",
            "useListener handlers that read a ref's .el",
            "useListener attaches at setup, so its handler runs before the "
            "component is in the DOM and every ref is null. A listener whose "
            "handler reads the DOM listens only while mounted: "
            "useMountedListener from @web/core/utils/hooks",
        )

    def test_no_patched_props(self):
        self._assert_per_repo(
            _scan_findings("owl_patched_props"),
            "owl_patched_props",
            "component props or defaultProps rewritten after the class is defined",
            "The owner exports its props (and defaultProps) object and points its "
            "static at it; a patch extends that object with Object.assign or push. "
            "OWL 3 reads props from the schema a component passes to useProps, so a "
            "rewritten static is lost",
        )

    def test_no_props_read_without_use_props(self):
        self._assert_per_repo(
            _unbound_props_findings(),
            "owl_unbound_props",
            "components that read this.props without a props = useProps(...) field, "
            "in static/src and static/tests",
            "An OWL 3 component has no this.props of its own: the constructor takes "
            "only the node, so this.props is undefined until the class declares "
            "props = useProps(this.constructor.props), and every read of it throws",
        )

    def test_no_extended_props_copied(self):
        self._assert_per_repo(
            _copied_props_findings(),
            "owl_copied_props",
            "components whose static props copy the exported props object a patch "
            "extends",
            "useProps exposes only the keys of the schema it is given, and a spread "
            "copies the exported object before any patch runs, so what the patch "
            "adds never reaches the component. Put the defaults in the exported "
            "object and point the static at it: static props = fooProps",
        )


@no_retry
class TestOwl3ApiScan(BaseCase):
    def test_every_gate_has_the_literal_its_matches_start_with(self):
        for gate, pattern in {**REMOVED_IN_OWL3, **ENV_KEYS}.items():
            with self.subTest(gate=gate):
                literal = required_literal(pattern)
                self.assertTrue(literal, "no prefilter: every file is searched")
                self.assertTrue(pattern.pattern.replace("\\", "").find(literal) >= 0)
        self.assertEqual(required_literal(re.compile(r"\bfoo|bar")), "")

    def test_an_import_of_a_name_owl_no_longer_exports_is_found(self):
        source = (
            "import {\n"
            "    Component,\n"
            "    useState,\n"
            "    proxy as makeProxy,\n"
            '} from "@odoo/owl";\n'
            '// import { useRef } from "@odoo/owl";\n'
            'import { useState } from "@web/core/somewhere";\n'
            "import { useRef, xml } from '@odoo/owl';\n"
        )
        exported = frozenset({"Component", "proxy", "xml"})
        self.assertEqual(removed_owl_imports(source, exported), [3, 8])

    def test_the_vendored_owl_is_read_for_what_it_exports(self):
        exported = owl_exports()
        self.assertIn("Component", exported)
        self.assertIn("mount", exported)
        self.assertNotIn("mount2", exported)

    def test_a_bare_call_is_found_and_a_method_of_that_name_is_not(self):
        source = (
            "onRendered(() => {});\n"
            "this.props.comp.onRendered(el);\n"
            "// onRendered(() => {});\n"
            "/* this.render() */ this.render(true);\n"
            "this.renderer();\n"
        )
        self.assertEqual(calls(REMOVED_IN_OWL3["owl_on_rendered"], source), [1])
        self.assertEqual(calls(REMOVED_IN_OWL3["owl_this_render"], source), [4])

    def test_a_class_with_its_own_render_calls_that_render(self):
        interaction = (
            "export class Countdown extends Interaction {\n"
            "    start() { this.render(); }\n"
            "    render() { draw(); }\n"
            "}\n"
        )
        self.assertEqual(calls(REMOVED_IN_OWL3["owl_this_render"], interaction), [])

    def test_a_sub_env_is_raw_unless_a_provider_makes_it(self):
        source = (
            "export function provideThing(thing) {\n"
            "    if (thing) { useSubEnv({ thing }); }\n"
            "}\n"
            "function provideChildThing({ a = 1 } = {}) {\n"
            "    useChildSubEnv({ a });\n"
            "}\n"
            "class C extends Component {\n"
            "    setup() { useSubEnv({ x: 1 }); }\n"
            "}\n"
            "// useSubEnv({ y: 1 });\n"
            "this.useSubEnv(x);\n"
        )
        self.assertEqual(raw_sub_env_calls(source), [8])

    def test_a_props_rewrite_is_found_and_an_owned_schema_extension_is_not(self):
        source = (
            "Foo.props = { ...Foo.props, a: String };\n"
            "Object.assign(Bar.props, extra);\n"
            "patch(Baz, {\n"
            "    components: { ...Baz.components },\n"
            "    defaultProps: { ...Baz.defaultProps, b: 1 },\n"
            "});\n"
            "patch(Baz.prototype, { props: 1 });\n"
            "Object.assign(fooProps, { a: String });\n"
            'barProps.push("b?");\n'
            "listView.props = (p) => p;\n"
            "if (Foo.props === other) {}\n"
            "// Foo.props = {};\n"
        )
        self.assertEqual(patched_props_calls(source), [1, 2, 5])

    def test_a_copy_of_an_extended_props_object_is_found_and_the_object_itself_is_not(
        self,
    ):
        owner = (
            "export const fooProps = { a: t.string(), b: t.number().optional() };\n"
            "export const barProps = { c: t.string() };\n"
            "export const bazProps = { d: t.string() };\n"
            "export class Foo extends Component {\n"
            "    static props = {\n"
            "        ...fooProps,\n"
            "        b: fooProps.b.optional(1),\n"
            "    };\n"
            "}\n"
            "export class Bar extends Component {\n"
            "    static props = barProps;\n"
            "}\n"
            "export class Baz extends Component {\n"
            "    static props = { ...bazProps, e: t.string() };\n"
            "}\n"
            "class Qux extends Foo {\n"
            "    // static props = { ...fooProps };\n"
            "    static props = { ...Foo.props };\n"
            "}\n"
        )
        patches = (
            "Object.assign(fooProps, { x: t.boolean().optional() });\n"
            "Object.assign(barProps, { y: t.boolean().optional() });\n"
            "// Object.assign(bazProps, {});\n"
        )
        extended = extended_objects(patches)
        self.assertEqual(extended, {"fooProps", "barProps"})
        self.assertEqual(copied_props_calls(owner, extended), [5])

    def test_a_props_read_is_unbound_unless_the_class_declares_use_props(self):
        source = (
            "export class Bound extends Component {\n"
            "    props = useProps(this.constructor.props);\n"
            "    setup() { this.props.onCreated(); }\n"
            "}\n"
            "export class Unbound extends Component {\n"
            '    static props = ["*"];\n'
            "    setup() { this.props.onCreated(); }\n"
            "}\n"
            "class Sub extends Bound {\n"
            "    setup() { this.props.onCreated(); }\n"
            "}\n"
            "class Silent extends Component {\n"
            '    static accept = "image/*";\n'
            "    // this.props.x\n"
            "}\n"
            "class Quiet extends Component {\n"
            '    label = "*/";\n'
            "    props = useProps();\n"
            "    get x() { return this.props.x; }\n"
            "}\n"
            "class InTemplate extends Component {\n"
            '    static template = xml`<t t-out="this.props.x"/>`;\n'
            "}\n"
        )
        self.assertEqual(unbound_props_reads(source), [5, 21])

    def test_a_listener_reaching_a_ref_through_its_callees_is_found(self):
        source = (
            "class C extends Component {\n"
            "    setup() {\n"
            '        useListener(window, "click", (ev) => {\n'
            "            this.root.el.contains(ev.target);\n"
            "        });\n"
            '        useListener(window, "keydown", this.onKeydown.bind(this));\n'
            "        const throttled = useThrottle(() => this.position());\n"
            '        useListener(window, "resize", throttled);\n'
            '        useListener(window, "blur", () => this.state.open = false);\n'
            '        useMountedListener(window, "scroll", () => this.root.el);\n'
            '        // useListener(window, "x", () => this.root.el);\n'
            "    }\n"
            "    onKeydown(ev) {\n"
            "        if (ev.key) { this.close(); }\n"
            "    }\n"
            "    close() {\n"
            "        this.menuRef.el?.blur();\n"
            "    }\n"
            "    position() {\n"
            "        const { top } = this.props.ref.el.getBoundingClientRect();\n"
            "    }\n"
            "}\n"
        )
        self.assertEqual(setup_listener_ref_reads(source), [3, 6, 8])

    def test_a_use_env_is_raw_unless_an_accessor_only_returns_it(self):
        source = (
            "export function useThing() {\n"
            "    return useEnv().thing;\n"
            "}\n"
            "function useBus() {\n"
            "    const env = useEnv();\n"
            "    return env.bus;\n"
            "}\n"
            "class C extends Component {\n"
            "    setup() { this.env = useEnv(); }\n"
            "}\n"
            "// useEnv();\n"
        )
        self.assertEqual(raw_use_env_calls(source), [5, 9])
