import functools
import re
from collections import defaultdict
from pathlib import Path

from odoo.modules import Manifest

from . import lint_case

HEX_RE = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")

NUMERIC_COLOUR_RE = re.compile(r"\b(?:rgba?|hsla?)\(\s*[\d.]")

BACKDROP_FILTER_RE = re.compile(r"(?<![\w-])(?:-webkit-)?backdrop-filter\s*:")

PAGE_PALETTE_RE = re.compile(r":root\s*\{[^{}]*\}")

CUSTOM_PROPERTY_RE = re.compile(r"--[\w-]+\s*:[^;{}]*")

MATERIAL_FILES = frozenset({"utils.scss"})

MOTION_DECLARATION_RE = re.compile(
    r"(?<![\w-])(?:transition|animation)(?:-duration)?\s*:([^;{}]*)"
)

VAR_CALL_RE = re.compile(r"var\([^()]*\)")

TIME_RE = re.compile(r"(?<![\w.$-])(\d*\.?\d+)m?s\b")

BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

LINE_COMMENT_RE = re.compile(r"(?<![:\w])//[^\n]*")

PALETTE_FILES = frozenset(
    {
        "tokens.scss",
        "palette_dark.scss",
        "primitives.scss",
        "primitives.dark.scss",
        "primary_variables.scss",
        "primary_variables.dark.scss",
        "bootstrap_overridden.scss",
        "bootstrap_overridden.dark.scss",
        "bs_functions_overridden.dark.scss",
    }
)

_SKIPPED_PARTS = frozenset({"lib", "tests", "node_modules"})

UPSTREAM_REPOS = frozenset({"design-themes"})


def is_palette(path: Path) -> bool:
    return path.name in PALETTE_FILES or path.name.endswith(
        (".variables.scss", "_variables.scss")
    )


def _without_comments(text: str) -> str:
    return LINE_COMMENT_RE.sub("", BLOCK_COMMENT_RE.sub(_keep_newlines, text))


def _lines(text: str, *patterns: re.Pattern) -> list[int]:
    text = _without_comments(text)
    return sorted(
        lint_case.line_of(text, match.start())
        for pattern in patterns
        for match in pattern.finditer(text)
    )


def colour_literals(text: str, *, plain_css: bool = False) -> list[int]:
    if plain_css:
        return page_colour_literals(text)
    return _lines(text, HEX_RE, NUMERIC_COLOUR_RE)


def page_colour_literals(text: str) -> list[int]:
    return colour_literals(
        PAGE_PALETTE_RE.sub(
            lambda block: CUSTOM_PROPERTY_RE.sub(_keep_newlines, block.group(0)),
            _without_comments(text),
        )
    )


def raw_backdrop_filters(text: str) -> list[int]:
    return _lines(text, BACKDROP_FILTER_RE)


def raw_durations(text: str) -> list[int]:
    text = _without_comments(text)
    return sorted(
        lint_case.line_of(text, declaration.start(1) + time.start())
        for declaration in MOTION_DECLARATION_RE.finditer(text)
        for time in TIME_RE.finditer(VAR_CALL_RE.sub(_blank, declaration.group(1)))
        if float(time.group(1))
    )


def _blank(match: re.Match) -> str:
    return " " * len(match.group(0))


def _keep_newlines(match: re.Match) -> str:
    return "\n" * match.group(0).count("\n")


@functools.cache
def _stylesheets() -> tuple[tuple[str, str, Path], ...]:
    sheets = []
    for manifest in Manifest.get_all_addon_manifests():
        static = Path(manifest.path) / "static"
        if manifest.name.startswith("test_") or not static.is_dir():
            continue
        repo = lint_case.repo_of(str(manifest.path))
        if repo in UPSTREAM_REPOS:
            continue
        for path in sorted(static.rglob("*.*ss")):
            if path.suffix not in (".scss", ".css") or is_palette(path):
                continue
            if _SKIPPED_PARTS.intersection(path.relative_to(static).parts):
                continue
            sheets.append((repo, manifest.name, path))
    return tuple(sheets)


def _relative(module: str, path: Path) -> Path:
    return path.relative_to(Path(Manifest.for_addon(module).path).parent)


def _findings(sheets, count) -> dict[str, list[str]]:
    findings = defaultdict(list)
    for repo, module, path in sheets:
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = path.relative_to(Path(Manifest.for_addon(module).path).parent)
        findings[repo].extend(f"{relative}:{line}" for line in count(text, path))
    return findings


def colour_literal_findings(sheets) -> dict[str, list[str]]:
    return _findings(
        sheets,
        lambda text, path: colour_literals(text, plain_css=path.suffix == ".css"),
    )


def backdrop_filter_findings(sheets) -> dict[str, list[str]]:
    return _findings(
        (
            (repo, module, path)
            for repo, module, path in sheets
            if not (module == "web" and path.name in MATERIAL_FILES)
        ),
        lambda text, _path: raw_backdrop_filters(text),
    )


def duration_findings(sheets) -> dict[str, list[str]]:
    return _findings(sheets, lambda text, _path: raw_durations(text))


class TestStyleLiterals(lint_case.LintCase):
    def test_what_counts_as_a_literal(self):
        sample = """
        a { color: #fff; background: #1c1c1eaa; }
        b { color: rgba(0, 0, 0, 0.5); border-color: hsl(210 100% 50%); }
        c { color: rgba($black, 0.5); background: var(--o-bg-view); }
        d { color: #{$link}; }
        /* e { color: #000; } */
        f { color: red; } // g { color: #123456; }
        h { background: url("//cdn.example/x.png"); }
        """
        self.assertEqual(colour_literals(sample), [2, 2, 3, 3])

    def test_a_plain_stylesheet_states_its_palette_in_root(self):
        sample = """
        :root {
            --page-accent: var(--tg-theme-button-color, #2481cc);
            --page-ink: #1c1c1e; /* } */
        }
        @media (prefers-color-scheme: dark) {
            :root { --page-ink: rgb(255 255 255); }
        }
        a { color: var(--page-ink); border-color: #fff; }
        """
        self.assertEqual(colour_literals(sample, plain_css=True), [9])
        self.assertEqual(colour_literals(sample), [3, 4, 7, 9])

    def test_a_fetched_page_states_its_palette_in_its_root(self):
        sample = """
        :root {
            --bg: var(--tg-theme-bg-color, #ffffff);
            --scrim: rgba(0, 0, 0, 0.55);
            color: #000;
        }
        a { color: #fff; --local: #123456; }
        """
        self.assertEqual(page_colour_literals(sample), [5, 7, 7])
        self.assertEqual(colour_literals(sample), [3, 4, 5, 7, 7])

    def test_colour_literals_only_go_down(self):
        found = colour_literal_findings(_stylesheets())
        self.assert_ratchet_per_repository(
            found,
            "colour_literals",
            "hard-coded colour(s) in <repo>'s stylesheets",
            "Read the colour from the palette: a token "
            "(o-token(--o-*, $fallback)), a palette variable, or a "
            "CSS colour function over one. A value only a palette "
            "file may state goes in the module's *.variables.scss; a "
            "plain .css page, which Sass does not reach, names it as a "
            "custom property in its :root block.",
        )

    def test_what_counts_as_a_raw_backdrop_filter(self):
        sample = """
        a { backdrop-filter: blur(4px); }
        b { -webkit-backdrop-filter: blur(4px); }
        c { transition: backdrop-filter 0.2s ease; }
        d { @include o-material("thin"); }
        /* e { backdrop-filter: none; } */
        """
        self.assertEqual(raw_backdrop_filters(sample), [2, 3])

    def test_raw_backdrop_filters_only_go_down(self):
        found = backdrop_filter_findings(_stylesheets())
        self.assert_ratchet_per_repository(
            found,
            "backdrop_filters",
            "raw backdrop-filter declaration(s) in <repo>'s stylesheets",
            'Use a material: @include o-material("ultrathin" | "thin" | '
            '"regular" | "thick"), or o-glass() for a material over the '
            "glass background. $o-materials in primary_variables.scss "
            "is the one definition.",
        )

    def test_what_counts_as_a_raw_duration(self):
        sample = """
        a { transition: opacity 0.2s ease, transform 150ms; }
        b { animation: o-fade 300ms $o-easing-spring; }
        c { transition-duration: 0s; animation-delay: 2s; }
        d { transition: all $o-duration-fast $o-easing-standard; }
        e { transition: opacity var(--o-duration-fast, 150ms); }
        """
        self.assertEqual(raw_durations(sample), [2, 2, 3])

    def test_raw_durations_only_go_down(self):
        found = duration_findings(_stylesheets())
        self.assert_ratchet_per_repository(
            found,
            "raw_durations",
            "hand-written transition/animation duration(s) in <repo>'s stylesheets",
            "Use a motion token: $o-duration-fast | -normal | -slow "
            "(or var(--o-duration-*)). They follow $o-durations and drop "
            "to 0s when the user asks for reduced motion.",
        )
