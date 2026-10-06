import argparse
import logging
import re
from io import BytesIO
from pathlib import Path

from lxml import etree

try:
    from ._xml_identity import PARSER
    from ._xml_rules import DataFile, dead_nolabels
except ImportError:
    from _xml_identity import PARSER
    from _xml_rules import DataFile, dead_nolabels

_logger = logging.getLogger(__name__)

_NOLABEL = re.compile(rb"""\s+nolabel\s*=\s*(["'])[^"']*\1""")


_COMMENT = re.compile(rb"<!--.*?-->", re.DOTALL)


def _attribute_spans(source: bytes) -> list[re.Match]:
    # every nolabel= written in a tag, in document order: one per element
    # carrying it, comments left out
    comments = [match.span() for match in _COMMENT.finditer(source)]
    return [
        match
        for match in _NOLABEL.finditer(source)
        if not any(start <= match.start() < end for start, end in comments)
    ]


def drop_dead_nolabels(path: Path, *, dry_run: bool = False) -> int | None:
    """Remove the nolabel= the form compiler never reads, in the file's own
    bytes; None when the file cannot be rewritten faithfully."""
    source = path.read_bytes()
    try:
        tree = etree.parse(BytesIO(source), PARSER)
    except etree.XMLSyntaxError as exc:
        _logger.warning("  SKIP  %s: %s", path, exc)
        return None
    file = DataFile(str(path), "", tree.getroot(), True, False)
    # the set holds the proxies: lxml hands out a new one per access once the
    # last reference is gone, so an id() taken here could name another element
    dead = {element for _record, element in dead_nolabels(file)}
    if not dead:
        return 0
    carriers = [
        element
        for element in tree.getroot().iter()
        if not callable(element.tag) and "nolabel" in element.attrib
    ]
    spans = _attribute_spans(source)
    if len(spans) != len(carriers):
        _logger.warning("  SKIP  %s: its nolabel= are not one per tag", path)
        return None
    out, cursor = [], 0
    for element, match in zip(carriers, spans, strict=True):
        if element not in dead:
            continue
        out.append(source[cursor : match.start()])
        cursor = match.end()
        del element.attrib["nolabel"]
    new_content = b"".join([*out, source[cursor:]])
    try:
        written = etree.parse(BytesIO(new_content), PARSER)
    except etree.XMLSyntaxError:
        return None
    if etree.tostring(tree, method="c14n") != etree.tostring(written, method="c14n"):
        _logger.warning("  SKIP  %s: another attribute would have moved", path)
        return None
    if any(dead_nolabels(DataFile(str(path), "", written.getroot(), True, False))):
        _logger.warning("  SKIP  %s: a dead nolabel would survive", path)
        return None
    if not dry_run:
        path.write_bytes(new_content)
    return len(dead)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=drop_dead_nolabels.__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    dropped = skipped = 0
    for raw in args.paths:
        root = Path(raw)
        for path in sorted(root.rglob("*.xml") if root.is_dir() else [root]):
            if "/static/" in str(path) or "node_modules" in path.parts:
                continue
            result = drop_dead_nolabels(path, dry_run=args.dry_run)
            if result is None:
                skipped += 1
            elif result:
                dropped += result
                _logger.info("  %d  %s", result, path)
    _logger.info(
        "%d nolabel attribute(s) dropped, %d file(s) skipped", dropped, skipped
    )


if __name__ == "__main__":
    main()
