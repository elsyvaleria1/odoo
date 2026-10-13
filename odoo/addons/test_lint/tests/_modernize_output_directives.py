import argparse
import logging
import re
from io import BytesIO
from pathlib import Path

from lxml import etree

_logger = logging.getLogger(__name__)

try:
    from . import _pretty_xml
except ImportError:
    import _pretty_xml

_PARSER = etree.XMLParser(remove_comments=False, strip_cdata=False)

RENAMES: dict[str, str] = {"t-esc": "t-out"}
_BYTE_RENAMES = {old.encode(): new.encode() for old, new in RENAMES.items()}

_NAME = rb"[A-Za-z_:][\w:.\-]*"
_VALUE = rb"\"[^\"]*\"|'[^']*'"
_ATTRIBUTE = re.compile(rb"(\s+)(" + _NAME + rb")(\s*=\s*)(" + _VALUE + rb")")
_MARKUP = re.compile(
    rb"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|<!DOCTYPE[^>]*>"
    rb"|<" + _NAME + rb"(?:\s+" + _NAME + rb"\s*=\s*(?:" + _VALUE + rb"))*\s*/?>",
    re.DOTALL,
)


def _rename(tag: bytes) -> bytes:
    if tag[1:2] in (b"!", b"?"):
        return tag
    names = {match.group(2) for match in _ATTRIBUTE.finditer(tag)}
    if not _BYTE_RENAMES.keys() & names:
        return tag
    if any(_BYTE_RENAMES[old] in names for old in _BYTE_RENAMES.keys() & names):
        return tag
    return _ATTRIBUTE.sub(
        lambda match: (
            match.group(1)
            + _BYTE_RENAMES.get(match.group(2), match.group(2))
            + match.group(3)
            + match.group(4)
        ),
        tag,
    )


def _shape(source: bytes, renames: dict[str, str]) -> list:
    root = etree.parse(BytesIO(source), _PARSER).getroot()
    out = []
    for element in root.iter():
        if callable(element.tag):
            out.append(("#comment", element.text))
            continue
        out.append(
            (
                element.tag,
                sorted((renames.get(k, k), v) for k, v in element.attrib.items()),
                (element.text or "").strip(),
                (element.tail or "").strip(),
            )
        )
    return out


def is_rename_only(source: bytes, rewritten: bytes) -> bool:
    try:
        return _shape(source, RENAMES) == _shape(rewritten, {})
    except etree.LxmlError:
        return False


def modernize_xml_file(path: Path, *, dry_run: bool = False) -> bool | None:
    source = path.read_bytes()
    try:
        etree.parse(BytesIO(source), _PARSER)
    except etree.XMLSyntaxError as exc:
        _logger.warning("  SKIP  %s: %s", path, exc)
        return None

    new_content = _MARKUP.sub(lambda match: _rename(match.group(0)), source)
    if new_content == source:
        return False

    if not is_rename_only(source, new_content):
        _logger.warning(
            "  SKIP  %s: the rewrite changes more than the directive names", path
        )
        return None

    if not dry_run:
        path.write_bytes(new_content)
    return True


def prepare_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Rename the deprecated t-esc output directive to t-out.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "roots",
        nargs="*",
        metavar="DIR",
        default=["."],
        help="Directories to search recursively (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Print which files would change without modifying them",
    )
    parser.add_argument(
        "--exclude",
        metavar="DIR",
        action="append",
        default=[],
        help=(
            "Extra directory names to skip, on top of the always-excluded "
            f"{', '.join(sorted(_pretty_xml.EXCLUDED_DIRS))}; repeatable"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = prepare_argument_parser().parse_args(argv)
    changed = unchanged = skipped = 0
    for xml_file in _pretty_xml.iter_target_files(args.roots, set(args.exclude)):
        result = modernize_xml_file(xml_file, dry_run=args.dry_run)
        if result is None:
            skipped += 1
        elif result:
            label = "would rename" if args.dry_run else "renamed     "
            print(f"  {label}  {xml_file}")
            changed += 1
        else:
            unchanged += 1
    verb = "would change" if args.dry_run else "renamed"
    print(f"\nDone: {changed} {verb}, {unchanged} unchanged, {skipped} skipped")


if __name__ == "__main__":
    main()
