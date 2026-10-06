from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.base.models.ir_access_explain import IrAccess
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona

MODEL = "test_access_right.shared_doc"


@tagged("post_install", "-at_install", "access_matrix")
class TestAccessMatrixRunner(AccessMatrixCase):
    personas = {
        "owner": Persona(),
        "reader": Persona(),
        "stranger": Persona(),
        "portal": Persona(portal="customer"),
    }
    cells = (
        Cell(MODEL, "doc", owner="rwcd", reader="r"),
        Cell(MODEL, "doc_b", note="another company's, no company guard", owner="rwcd"),
    )

    @classmethod
    def build(cls):
        docs = cls.env[MODEL].with_user(cls.users["owner"])
        return {
            "doc": docs.create(
                {"name": "doc", "reader_ids": [(4, cls.users["reader"].id)]}
            ),
            "doc_b": docs.create({"name": "b", "company_id": cls.companies["b"].id}),
        }

    def _fails(self, cells, needle):
        self.cells = cells
        with self.assertRaises(AssertionError) as raised:
            self._test_access_matrix()
        self.assertIn(needle, str(raised.exception))

    def test_a_cell_the_system_does_not_honour(self):
        self._fails(
            (Cell(MODEL, "doc", owner="rwcd", reader="rw"),),
            "doc reader write: matrix=True check=False filter=False explain=False",
        )

    def test_a_persona_left_out_expects_nothing(self):
        self._fails(
            (Cell(MODEL, "doc", owner="rwcd"),),
            "doc reader read: matrix=False check=True",
        )

    def test_a_check_that_disagrees_with_the_filter(self):
        real = type(self.env[MODEL]).has_access

        def lying(records, operation):
            return True if records._name == MODEL else real(records, operation)

        with patch.object(type(self.env[MODEL]), "has_access", lying):
            self._fails(self.cells, "doc stranger read: matrix=False check=True")

    def test_an_explanation_that_disagrees(self):
        real = IrAccess._explain_record

        def lying(ir_access, record, operation):
            explanation = real(ir_access, record, operation)
            for entry in explanation["permissions"]:
                entry["admits"] = True
            return explanation

        with patch.object(IrAccess, "_explain_record", lying):
            self._fails(self.cells, "doc stranger read: matrix=False check=False")

    def test_a_deviation_names_its_finding_and_is_asserted(self):
        with self.assertRaises(ValueError):
            Cell(MODEL, "doc", today={"reader": "rw"})
        self.cells = (
            Cell(
                MODEL,
                "doc",
                owner="rwcd",
                finding="planted: the reader may not read",
                today={"reader": "r"},
            ),
        )
        self._test_access_matrix()
        self._fails(
            (
                Cell(
                    MODEL,
                    "doc",
                    owner="rwcd",
                    reader="r",
                    finding="planted: a deviation that no longer holds",
                    today={"reader": "rw"},
                ),
            ),
            "doc reader write: matrix=False check=False filter=False explain=False "
            "(today's deviation expects",
        )

    def test_a_co_installed_module_adds_and_withdraws_only_when_installed(self):
        self.cells = (
            Cell(
                MODEL,
                "doc",
                owner="rwcd",
                reader="rw",
                installed={"base": {"reader": "-w"}},
            ),
            Cell(
                MODEL,
                "doc_b",
                installed={"base": {"owner": "rwcd"}, "base_absent": {"owner": "-r"}},
            ),
        )
        self._test_access_matrix()
        self._fails(
            (
                Cell(
                    MODEL,
                    "doc",
                    owner="rwcd",
                    reader="r",
                    installed={"base_absent": {"reader": "w"}},
                ),
                Cell(
                    MODEL,
                    "doc_b",
                    owner="rwcd",
                    installed={"base": {"owner": "-d"}},
                ),
            ),
            "doc_b owner unlink: matrix=False check=True",
        )

    def test_an_adjustment_names_known_personas_and_operations(self):
        self._fails(
            (Cell(MODEL, "doc", owner="rwcd", installed={"base": {"ghost": "r"}}),),
            "unknown persona(s) {'ghost'}",
        )
        self._fails(
            (Cell(MODEL, "doc", owner="rwcd", installed={"base": {"reader": "-z"}}),),
            "not operations {'z'}",
        )
