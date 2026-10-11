#!/usr/bin/env python3

"""
Checks versions from the requirements files against distribution-provided
versions, taking distribution's Python version in account e.g. if checking
against a release which bundles Python 3.5, checks the 3.5 version of
requirements.

* only shows requirements for which at least one release diverges from the
  matching requirements version
* empty or green cells mean that specific release matches its requirement (happens when
  checking multiple releases: one of the other releases may mismatch the its
  requirements necessating showing the row)

This script was heavily reworked but is not in a final version:
TODO:
- add legends
- better management of cache
- add meta info on cells (mainly to genearte a better html report)
    - warn/ko reason
    - wheel + link
    - original debian package name + link
    ...

"""

import argparse
import gzip
import itertools
import json
import re
import shutil
import tempfile

try:
    import ansitoimg
except ImportError:
    ansitoimg = None

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from sys import stderr, stdout
from typing import TYPE_CHECKING
from urllib.parse import urlsplit
from urllib.request import HTTPError
from urllib.request import urlopen as _urlopen

from packaging.markers import Marker
from packaging.requirements import Requirement
from packaging.tags import mac_platforms
from packaging.utils import canonicalize_name
from pip._internal.index.package_finder import (
    LinkEvaluator,
)
from pip._internal.models.link import Link
from pip._internal.models.target_python import TargetPython

if TYPE_CHECKING:
    import io

Version = tuple[int, ...]

SPECIAL = {
    "pytz": "tz",
    "protobuf": "protobuf",
}
SUPPORTED_FORMATS = ("txt", "ansi", "svg", "html", "json")
PLATFORM_CODES = ("linux", "win32", "darwin")
PLATFORM_NAMES = ("Linux", "Win", "OSX")


def urlopen(url: str) -> io.BufferedReader:
    if urlsplit(url).scheme not in ("http", "https"):
        raise ValueError("Package metadata URLs must use HTTP or HTTPS")
    file_name = "".join(c if c.isalnum() else "_" for c in url)
    Path("/tmp/package_versions_cache/").mkdir(exist_ok=True, parents=True)
    file_path = f"/tmp/package_versions_cache/{file_name}"
    if not Path(file_path).is_file():
        with _urlopen(url) as response:
            Path(file_path).write_bytes(response.read())
    return Path(file_path).open("rb")


def parse_version(vstring: str) -> Version | None:
    if not vstring:
        return None
    return tuple(map(int, vstring.split(".")))


def cleanup_debian_version(s: str) -> str:
    return re.match(
        r"""
        (?:\d+:)? # debian crud prefix
        (.*?) # the shit we actually want
        (?:~|\+|-|\.dfsg)
        .*
    """,
        s,
        flags=re.VERBOSE,
    )[1]


class PipPackage:
    """Wrapper around PyPI JSON API data for a single package."""

    def __init__(self, name: str) -> None:
        self.name = name
        infos = json.load(urlopen(f"https://pypi.org/pypi/{name}/json"))
        self.info = infos["info"]
        self.last_serial = infos["last_serial"]
        self.releases = infos["releases"]
        self.urls = infos["urls"]
        self.vulnerabilities = infos["vulnerabilities"]

    def get_wheel_availability(
        self, version: str | None, python_version: str, platform: str
    ) -> tuple[bool, bool, bool]:
        if version is None:
            return (False, False, False)
        py_version_info = python_version.split(".")
        if len(py_version_info) == 2:
            py_version_info = (py_version_info[0], py_version_info[1], 0)
        releases = self.releases
        has_wheel_for_version = False
        has_any_wheel = False
        has_wheel_in_another_version = False
        platforms = None
        if platform == "darwin":
            platforms = list(mac_platforms((15, 0), "x86_64"))
        elif platform == "win32":
            platforms = ["win32", "win-amd64"]
        else:
            assert platform == "linux"

        target_python = TargetPython(
            platforms=platforms,
            py_version_info=py_version_info,
            abis=None,
            implementation=None,
        )
        le = LinkEvaluator(
            project_name=self.name,
            canonical_name=canonicalize_name(self.name),
            formats={"binary", "source"},
            target_python=target_python,
            allow_yanked=True,
            ignore_requires_python=False,
        )
        for release in releases[version]:
            if release["filename"].endswith(".whl"):
                has_any_wheel = True
            is_candidate, _result = le.evaluate_link(
                Link(
                    comes_from=None,
                    url=release["url"],
                    requires_python=release["requires_python"],
                    yanked_reason=release["yanked_reason"],
                )
            )
            if is_candidate:
                if release["filename"].endswith(".whl"):
                    has_wheel_for_version = has_wheel_in_another_version = True
                break

        if not has_wheel_for_version and has_any_wheel:
            for rel_version, rel in releases.items():
                for release in rel:
                    if not release["filename"].endswith(".whl"):
                        continue
                    if any(
                        not s.isdigit() for s in rel_version.split(".")
                    ) or parse_version(rel_version) <= parse_version(version):
                        continue
                    is_candidate, _result = le.evaluate_link(
                        Link(
                            comes_from=None,
                            url=release["url"],
                            requires_python=release["requires_python"],
                            yanked_reason=release["yanked_reason"],
                        )
                    )
                    if is_candidate:
                        has_wheel_in_another_version = True
                        stderr.write(
                            f"WARNING: Wheel found for {self.name} ({python_version} {platform}) in {rel_version}\n"
                        )
                        return (
                            has_wheel_for_version,
                            has_any_wheel,
                            has_wheel_in_another_version,
                        )

        return (has_wheel_for_version, has_any_wheel, has_wheel_in_another_version)


class Distribution(ABC):
    """Abstract base for distribution package checkers."""

    def __init__(self, release: str) -> None:
        self._release = release

    @abstractmethod
    def get_version(self, package: str) -> Version | None: ...

    def __str__(self) -> str:
        return f"{type(self).__name__.lower()} {self._release}"

    @classmethod
    def get(cls, name: str) -> type[Distribution]:
        try:
            return next(c for c in cls.__subclasses__() if c.__name__.lower() == name)
        except StopIteration:
            msg = f"Unknown distribution {name!r}"
            raise ValueError(msg) from None


class Debian(Distribution):
    """Checker for Debian distribution package versions via sources.debian.org API."""

    def get_version(self, package: str) -> Version | str | None:
        package = SPECIAL.get(package, package)
        prefixes = ["python-", ""]
        if package.startswith("python"):
            prefixes = [""]
        for prefix in prefixes:
            try:
                res = json.load(
                    urlopen(f"https://sources.debian.org/api/src/{prefix}{package}/")
                )
            except HTTPError:
                return "failed"
            if res.get("error") is None:
                break
        if res.get("error"):
            return None

        try:
            return next(
                parse_version(cleanup_debian_version(distr["version"]))
                for distr in res["versions"]
                if distr["area"] == "main"
                if self._release.lower() in distr["suites"]
            )
        except StopIteration:
            return None


class Ubuntu(Distribution):
    """Ubuntu doesn't have an API, instead it has a huge text file"""

    def __init__(self, release: str) -> None:
        super().__init__(release)

        self._packages = {}
        with (
            urlopen(
                f"https://packages.ubuntu.com/source/{release}/allpackages?format=txt.gz"
            ) as response,
            gzip.open(response, mode="rt", encoding="utf-8") as data,
        ):
            for line in itertools.islice(
                data, 6, None
            ):
                m = re.match(r"(\S+) \(([^)]+)\)", line.strip())
                assert m, f"invalid line {line.strip()!r}"
                self._packages[m[1]] = m[2]

    def get_version(self, package: str) -> Version | None:
        package = SPECIAL.get(package, package)
        for prefix in ["python3-", "python-", ""]:
            v = self._packages.get(f"{prefix}{package}")
            if v:
                return parse_version(cleanup_debian_version(v))
        return None


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].strip()


def parse_requirements(reqpath: Path) -> dict[str, list[tuple[str, Marker]]]:
    reqs = {}
    with reqpath.open("r", encoding="utf-8") as f:
        for req_line in f:
            req_line = _strip_comment(req_line)
            if not req_line:
                continue
            requirement = Requirement(req_line)
            version = None
            if requirement.specifier:
                floors = [
                    spec
                    for spec in requirement.specifier
                    if spec.operator in ("==", ">=", "~=")
                ]
                if not floors:
                    msg = (
                        f"{requirement.name}: no lower bound in "
                        f"{str(requirement.specifier)!r}, nothing to compare"
                    )
                    raise NotImplementedError(msg)
                version = floors[0].version
            reqs.setdefault(requirement.name, []).append((version, requirement.marker))
    return reqs


def ok(text: str) -> str:
    return f"\033[92m{text}\033[39m"


def em(text: str) -> str:
    return f"\033[94m{text}\033[39m"


def warn(text: str) -> str:
    return f"\033[93m{text}\033[39m"


def ko(text: str) -> str:
    return f"\033[91m{text}\033[39m"


def default(text: str) -> str:
    return text


def _requirements(args: argparse.Namespace) -> dict[str, list[tuple[str, Marker]]]:
    repo_root = (Path.cwd() / __file__).parent.parent
    reqs = parse_requirements(repo_root / "requirements.txt")
    for name, options in parse_requirements(
        repo_root / "requirements-addons.txt"
    ).items():
        reqs.setdefault(name, []).extend(options)
    if args.filter:
        reqs = {
            r: o for r, o in reqs.items() if any(f in r for f in args.filter.split(","))
        }
    return reqs


def _header_rows(
    uniq: list[str], platforms: Sequence[str], checkers: list, pyvers: list[str]
) -> list[list]:
    platform_headers = [""]
    python_headers = [""]
    for v in uniq:
        for p in platforms:
            platform_headers.append(p)
            python_headers.append(v)
    for checker, version in zip(checkers, pyvers, strict=False):
        platform_headers.append(checker._release[:5])
        python_headers.append(version)
    return [platform_headers, python_headers]


def _matching_version(
    options: list[tuple[str, Marker]], pyver: str, platform: str
) -> tuple[bool, str | None]:
    for version, markers in options:
        if not markers or markers.evaluate(
            {"python_version": pyver, "sys_platform": platform}
        ):
            return True, version
    return False, None


def _pypi_deco(
    pip_infos: PipPackage,
    platform_version: str,
    pyver: str,
    platform: str,
    byver: dict[str, str],
) -> str | None:
    deco = None
    if platform_version == "none":
        deco = "ok"
    else:
        has_wheel_for_version, has_any_wheel, has_wheel_in_another_version = (
            pip_infos.get_wheel_availability(platform_version, pyver, platform)
        )
        if has_wheel_for_version:
            deco = "ok"
        elif has_wheel_in_another_version:
            deco = "ko"
        elif has_any_wheel:
            deco = "warn"
    if deco in ("ok", None) and byver.get(pyver, "none") != platform_version:
        deco = "em"
    return deco


def _distro_deco(req_version: str, check_version: str | None) -> str:
    if req_version == "none":
        return "ok"
    if req_version == "any":
        return "ok" if check_version is None else "ko"
    if check_version is None:
        return "ko"
    if parse_version(req_version) >= parse_version(check_version):
        return "warn"
    return "ko"


def _requirement_row(
    req: str,
    options: list[tuple[str, Marker]],
    args: argparse.Namespace,
    uniq: list[str],
    platform_codes: Sequence[str],
    checkers: list,
    pyvers: list[str],
) -> list | None:
    pip_infos = PipPackage(req) if args.check_pypi else None
    row: list = [req]
    byver: dict[str, str] = {}
    for pyver in uniq:
        for platform in platform_codes:
            matched, match = _matching_version(options, pyver, platform)
            if matched and platform == "linux":
                byver[pyver] = match
            platform_version = match if matched else "none"
            deco = None
            if pip_infos is not None:
                deco = _pypi_deco(pip_infos, platform_version, pyver, platform, byver)
            row.append((platform_version or "any", deco))
    if not byver and not args.all:
        return None
    for checker, pyver in zip(checkers, pyvers, strict=False):
        req_version = byver.get(pyver, "none") or "any"
        check_version = (
            ".".join(map(str, checker.get_version(req.lower()) or [])) or None
        )
        if req_version != check_version:
            row.append(
                (check_version or "</>", _distro_deco(req_version, check_version))
            )
        elif args.all:
            row.append((check_version or "</>", "ok"))
        else:
            row.append("")
    return row


def _separators(n_pyvers: int, n_platforms: int, n_checkers: int) -> list[str]:
    seps = [" || "]
    for _ in range(n_pyvers):
        seps[-1] = " || "
        seps.extend([" | "] * n_platforms)
    seps[-1] = " |#| "
    seps.extend([" |#|  "] * n_checkers)
    seps[-1] = " "
    return seps


def _output_format(args: argparse.Namespace) -> str:
    if args.format:
        assert args.format in SUPPORTED_FORMATS
        return args.format
    if args.output:
        ext = args.output.split(".")[-1]
        return ext if ext in SUPPORTED_FORMATS else "txt"
    return "ansi"


def _render_text(
    table: list[list], sizes: list[int], seps: list[str], output_format: str
) -> str:
    level_decos = {"ok": ok, "em": em, "warn": warn}
    output = ""
    for row in table:
        output += " "
        for cell, width, sep in zip(row, sizes, seps, strict=False):
            cell_content = cell
            deco = default
            if isinstance(cell, tuple):
                cell_content, level = cell
                if output_format != "txt" and level is not None:
                    deco = level_decos.get(level, ko)
            output += deco(f"{cell_content:<{width}}") + sep
        output += "\n"
    return output


def _to_image(output: str, output_format: str, width: int) -> str:
    if not ansitoimg:
        stderr.write(f"Missing ansitoimg for {output_format} format, switching to ansi")
        return output
    convert = ansitoimg.ansiToHTML if output_format == "html" else ansitoimg.ansiToSVG
    with tempfile.NamedTemporaryFile() as tmp:
        convert(output, tmp.name, width=width, title="requirements-check.py")
        output = tmp.read().decode()
    return output.replace(
        """<g transform="translate(26,22)">
            <circle cx="0" cy="0" r="7" fill="#ff5f57"/>
            <circle cx="22" cy="0" r="7" fill="#febc2e"/>
            <circle cx="44" cy="0" r="7" fill="#28c840"/>
            </g>""",
        "",
    )


def main(args: argparse.Namespace) -> None:
    checkers = [
        Distribution.get(distro)(release)
        for version in args.release
        for (distro, release) in [version.split(":")]
    ]

    stderr.write("Fetch Python versions...\n")
    pyvers = [
        ".".join(map(str, checker.get_version("python3-defaults")[:2]))
        for checker in checkers
    ]

    uniq = sorted(set(pyvers), key=parse_version)
    platforms = PLATFORM_NAMES if args.check_pypi else PLATFORM_NAMES[:1]
    platform_codes = PLATFORM_CODES if args.check_pypi else PLATFORM_CODES[:1]
    table = _header_rows(uniq, platforms, checkers, pyvers)
    for req, options in _requirements(args).items():
        row = _requirement_row(
            req, options, args, uniq, platform_codes, checkers, pyvers
        )
        if row is not None:
            table.append(row)
    seps = _separators(len(uniq), len(platform_codes), len(checkers))

    stderr.write("\n")

    sizes = [0] * len(table[0])
    for row in table:
        sizes = [
            max(s, len(cell[0] if isinstance(cell, tuple) else cell))
            for s, cell in zip(sizes, row, strict=False)
        ]

    output_format = _output_format(args)
    if output_format == "json":
        output = json.dumps(table)
    else:
        output = _render_text(table, sizes, seps, output_format)
    if output_format in ("svg", "html"):
        output = _to_image(
            output, output_format, sum(sizes) + sum(len(sep) for sep in seps)
        )

    if args.output:
        Path(args.output).write_text(output, encoding="utf8")
    else:
        stdout.write(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "release",
        nargs="+",
        help="Release to check against, should use the format '{distro}:{release}' e.g. 'debian:sid'",
    )
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="Display all requirements even if it matches",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="output path",
    )
    parser.add_argument(
        "-f",
        "--format",
        help=f"Supported format: {', '.join(SUPPORTED_FORMATS)}",
    )
    parser.add_argument(
        "--update-cache",
        action="store_true",
        help="Ignore the existing package version cache and update them",
    )
    parser.add_argument(
        "--check-pypi",
        action="store_true",
        help="Check wheel packages",
    )
    parser.add_argument(
        "--filter",
        help="Comma sepaated list of package to check",
    )

    args = parser.parse_args()
    if args.update_cache:
        shutil.rmtree("/tmp/package_versions_cache/")
    main(args)
