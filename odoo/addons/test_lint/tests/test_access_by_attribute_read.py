import ast
from collections import defaultdict

from . import _production_python, lint_case

_READS = frozenset(
    {
        "browse",
        "mapped",
        "filtered",
        "filtered_domain",
        "grouped",
        "sorted",
        "exists",
        "check_singleton",
        "with_context",
        "with_company",
        "get",
        "append",
        "len",
        "bool",
        "str",
        "int",
        "next",
        "iter",
        "isinstance",
    }
)


def _catches_access_error(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return False
    return any(
        (isinstance(node, ast.Name) and node.id == "AccessError")
        or (isinstance(node, ast.Attribute) and node.attr == "AccessError")
        for node in ast.walk(handler.type)
    )


def _called(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def _writes_another_record(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Assign):
        targets = statement.targets
    elif isinstance(statement, ast.AugAssign):
        targets = [statement.target]
    else:
        return False
    return any(
        isinstance(target, ast.Attribute) and not isinstance(target.value, ast.Name)
        for target in targets
    )


def _decides_by_reading(body: list[ast.stmt]) -> bool:
    for statement in body:
        if _writes_another_record(statement):
            return False
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and _called(node) not in _READS:
                return False
    return any(
        isinstance(node, ast.Attribute)
        for statement in body
        for node in ast.walk(statement)
    )


def _sites(tree: ast.Module) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Try)
        and any(_catches_access_error(handler) for handler in node.handlers)
        and _decides_by_reading(node.body)
    ]


def access_by_attribute_read_findings(sources) -> dict[str, list[str]]:
    found: dict[str, list[str]] = defaultdict(list)
    by_path = _production_python.extract(_sites, (path for *_, path in sources))
    for repo, _module, path in sources:
        for line in by_path[path] or ():
            found[repo].append(f"{path}:{line}")
    return found


class TestAccessByAttributeRead(lint_case.LintCase):
    def test_no_access_decision_is_left_to_an_attribute_read(self):
        sources = _production_python.production_sources()
        self.assert_ratchet_per_repository(
            access_by_attribute_read_findings(sources),
            "access_by_attribute_read",
            "try block(s) in <repo> deciding access by whether reading a field "
            "raises AccessError",
            "A read raises only when the value is fetched: once a sudo read or an "
            "access check has cached it, the same read returns it, so the branch "
            "taken depends on what ran before. Decide explicitly: "
            "_filtered_access(operation) for the records, has_access() for one, "
            "_visible_display_names() for names shown or withheld.",
        )

    def test_the_scan_tells_a_read_from_a_decision(self):
        def sites(source: str) -> list[int]:
            return _sites(ast.parse(source))

        self.assertEqual(
            sites(
                "try:\n    name = record.partner_id.name\n"
                "except AccessError:\n    name = ''\n"
            ),
            [1],
        )
        self.assertEqual(
            sites(
                "try:\n    record.check_access('read')\nexcept AccessError:\n    pass\n"
            ),
            [],
        )
        self.assertEqual(
            sites(
                "try:\n    rows = records.read(['name'])\nexcept AccessError:\n    pass\n"
            ),
            [],
        )
        self.assertEqual(
            sites(
                "try:\n    self.message_id.body = body\nexcept AccessError:\n    pass\n"
            ),
            [],
            "an assignment through a relation is a write, which checks",
        )
        self.assertEqual(
            sites(
                "try:\n    env['res.partner'].browse(1).name = name\n"
                "except AccessError:\n    pass\n"
            ),
            [],
        )
        self.assertEqual(
            sites(
                "try:\n    name = record.name\n"
                "except (MissingError, AccessError):\n    name = ''\n"
            ),
            [1],
        )
