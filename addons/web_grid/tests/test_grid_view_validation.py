from lxml import etree

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import view_validation

from ..validation import valid_field_types


@tagged("post_install", "-at_install")
class TestGridViewValidation(TransactionCase):
    """The grid arch is described in three places -- the RelaxNG schema,
    valid_field_types and GridArchParser -- and nothing compares the three.
    These pin the two that run server-side against each other.
    """

    def _arch(self, body):
        return etree.fromstring(f'<grid string="Test">{body}</grid>')

    def _schema(self, body):
        return view_validation.relaxng("grid").validate(self._arch(body))

    def test_the_schema_is_declared_and_loads(self):
        self.assertEqual(
            view_validation.registered_schemas().get("grid"),
            "web_grid/rng/grid_view.rng",
        )
        self.assertIsNotNone(view_validation.relaxng("grid"))

    def test_bare_field_is_a_row(self):
        body = '<field name="a"/><field name="d" type="col"/>'
        self.assertTrue(self._schema(body))
        self.assertTrue(valid_field_types(self._arch(body)))

    def test_row_fields_are_not_limited(self):
        body = (
            '<field name="a" type="row"/><field name="b" type="row"/><field name="c"/>'
        )
        self.assertTrue(self._schema(body))
        self.assertTrue(valid_field_types(self._arch(body)))

    def test_col_measure_and_readonly_appear_at_most_once(self):
        for field_type in ("col", "measure", "readonly"):
            body = (
                f'<field name="a" type="{field_type}"/>'
                f'<field name="b" type="{field_type}"/>'
            )
            with self.subTest(field_type=field_type):
                self.assertFalse(
                    valid_field_types(self._arch(body)),
                    f"a second {field_type} field must be refused",
                )

    def test_schema_refuses_an_unknown_field_type(self):
        self.assertFalse(self._schema('<field name="a" type="measur"/>'))

    def test_schema_requires_at_least_one_field(self):
        self.assertFalse(self._schema(""))

    def test_schema_accepts_a_row_granularity(self):
        self.assertTrue(
            self._schema(
                '<field name="d" type="row" granularity="month"/>'
                '<field name="c" type="col"/>'
            )
        )

    def test_schema_refuses_an_unknown_granularity(self):
        self.assertFalse(
            self._schema('<field name="d" type="row" granularity="fortnight"/>')
        )

    def test_an_invalid_grid_view_cannot_be_stored(self):
        with self.assertRaises(ValidationError):
            self.env["ir.ui.view"].create(
                {
                    "name": "invalid grid",
                    "model": "res.partner",
                    "type": "grid",
                    "arch": """
                        <grid string="Partners">
                            <field name="name" type="measure"/>
                            <field name="color" type="measure"/>
                        </grid>
                    """,
                }
            )

    def test_an_arch_only_the_schema_refuses_cannot_be_stored(self):
        fieldless = "<grid string='Partners'></grid>"
        self.assertTrue(
            valid_field_types(etree.fromstring(fieldless)),
            "the other predicate must accept it, or this proves nothing",
        )
        with self.assertRaises(ValidationError):
            self.env["ir.ui.view"].create(
                {
                    "name": "schema-invalid grid",
                    "model": "res.partner",
                    "type": "grid",
                    "arch": fieldless,
                }
            )


@tagged("post_install", "-at_install")
class TestGridViewModeScrub(TransactionCase):
    """Deleting a model's last grid view takes ``grid`` out of its window
    actions, rows included. This used to be web_grid's own ``unlink`` and is
    base's for every view type without a default arch now; the grid is the
    type that exercises the act_window.view rows.
    """

    def _grid_view(self, name):
        return self.env["ir.ui.view"].create(
            {
                "name": name,
                "model": "res.partner",
                "type": "grid",
                "arch": """
                    <grid string="Partners">
                        <field name="name" type="row"/>
                        <field name="color" type="measure"/>
                    </grid>
                """,
            }
        )

    def test_last_grid_view_leaves_the_action_and_its_rows(self):
        view = self._grid_view("scrub grid")
        action = self.env["ir.actions.act_window"].create(
            {
                "name": "partners",
                "res_model": "res.partner",
                "view_mode": "grid,list",
                "view_ids": [
                    (0, 0, {"view_mode": "grid", "view_id": view.id, "sequence": 1}),
                    (0, 0, {"view_mode": "list", "sequence": 2}),
                ],
            }
        )
        view.unlink()
        self.assertEqual(action.view_mode, "list")
        self.assertEqual(action.view_ids.mapped("view_mode"), ["list"])
        self.assertEqual([mode for _, mode in action.views], ["list"])

    def test_another_grid_view_keeps_the_action(self):
        first = self._grid_view("scrub grid a")
        self._grid_view("scrub grid b")
        action = self.env["ir.actions.act_window"].create(
            {"name": "partners", "res_model": "res.partner", "view_mode": "grid,list"}
        )
        first.unlink()
        self.assertEqual(action.view_mode, "grid,list")
