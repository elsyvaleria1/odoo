import functools
import re

from odoo.modules import Manifest

from . import _js_sources, lint_case

_COMMENT = re.compile(r"/\*.*?\*/|//[^\n]*", re.DOTALL)
_DROPPED_CLAIM = re.compile(
    r"^[ \t]*(?:[\w$]+\.)*(?:bus_service|busService|bus)\.(?:addChannel|subscribe)\(",
    re.MULTILINE,
)


def _starts_a_statement(code: str, at: int) -> bool:
    before = code[:at].rstrip()
    return not before or before[-1] in ";{}"


def dropped_claims(source: str) -> list[int]:
    code = _COMMENT.sub(lambda m: "\n" * m.group().count("\n"), source)
    return [
        code.count("\n", 0, m.start()) + 1
        for m in _DROPPED_CLAIM.finditer(code)
        if _starts_a_statement(code, m.start())
    ]


@functools.cache
def _findings() -> dict[str, tuple[str, ...]]:
    repo_by_addon = {
        manifest.name: lint_case.repo_of(manifest.path)
        for manifest in Manifest.get_all_addon_manifests()
    }
    found: dict[str, list[str]] = {}
    for addon, path, source in _js_sources.addon_js_outside_lib():
        if "/static/src/" in path.as_posix() and not _js_sources.vendored(path):
            found.setdefault(repo_by_addon[addon], []).extend(
                f"{path}:{line}" for line in dropped_claims(source)
            )
    return {repo: tuple(items) for repo, items in sorted(found.items())}


class TestBusClaims(lint_case.LintCase):
    def test_no_dropped_bus_claim(self):
        self.assert_ratchet_per_repository(
            _findings(),
            "bus_dropped_claim",
            "bus channel claims and subscriptions whose release is dropped in <repo>",
            "addChannel and subscribe return their release: a component claims "
            "through useBusChannel / useBusSubscription, anything else keeps the "
            "release and calls it when its owner ends. Only an owner that lives "
            "as long as the page may drop it",
        )


class TestBusClaimsSeeTheirFaults(lint_case.LintCase):
    def test_a_dropped_claim_is_found_and_a_kept_one_is_not(self):
        source = (
            "this.busService.addChannel(channel);\n"
            "const release = busService.addChannel(channel);\n"
            "// bus.subscribe('x', f);\n"
            "    this.env.services.bus_service.subscribe('x', f);\n"
            "return bus.subscribe('x', f);\n"
            "onWillDestroy(bus.subscribe('x', f));\n"
            "this.release =\n"
            "    bus.addChannel(channel);\n"
            "this.registerCleanup(\n"
            "    busService.subscribe('x', f),\n"
            ");\n"
            "if (x) {\n"
            "    bus.addChannel(channel);\n"
            "}\n"
        )
        self.assertEqual(dropped_claims(source), [1, 4, 13])
