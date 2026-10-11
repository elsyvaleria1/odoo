import json

from odoo.libs.json import loads as json_loads

from . import lint_case


class TestFloors(lint_case.LintCase):
    def test_the_floors_file_has_one_spelling(self):
        text = lint_case._FLOORS_PATH.read_text(encoding="utf-8")
        floors = json_loads(text)
        self.assertEqual(
            [gate for gate, floor in floors.items() if floor == 0],
            [],
            "drop these entries: an absent gate is a hard zero",
        )
        self.assertFalse(
            [
                gate
                for gate, floor in floors.items()
                if type(floor) is not int or floor < 0
            ],
            "a floor is a count",
        )
        self.assertEqual(
            text,
            json.dumps(dict(sorted(floors.items())), indent=2) + "\n",
            f"write {lint_case._FLOORS_PATH.name} with sorted keys and a "
            "two-space indent",
        )
