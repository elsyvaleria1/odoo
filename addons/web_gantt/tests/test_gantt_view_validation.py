from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestGanttViewValidation(TransactionCase):
    def _create_gantt_view(self, arch):
        return self.env["ir.ui.view"].create(
            {
                "name": "Gantt validation probe",
                "model": "res.company",
                "type": "gantt",
                "arch": arch,
            }
        )

    def test_valid_gantt_view_is_accepted(self):
        view = self._create_gantt_view(
            '<gantt date_start="create_date" date_stop="write_date" string="Probe">'
            '<field name="name"/>'
            "</gantt>"
        )

        self.assertEqual(view.type, "gantt")

    def test_single_templates_tag_is_accepted(self):
        view = self._create_gantt_view(
            '<gantt date_start="create_date" date_stop="write_date"><templates/></gantt>'
        )

        self.assertEqual(view.type, "gantt")

    def test_gantt_requires_date_start(self):
        with self.assertRaisesRegex(
            ValidationError, "must have a 'date_start' attribute"
        ):
            self._create_gantt_view('<gantt date_stop="write_date" string="Probe"/>')

    def test_gantt_requires_date_stop(self):
        with self.assertRaisesRegex(
            ValidationError, "must have a 'date_stop' attribute"
        ):
            self._create_gantt_view('<gantt date_start="create_date" string="Probe"/>')

    def test_gantt_rejects_unknown_default_scale(self):
        with self.assertRaisesRegex(ValidationError, "Invalid default_scale 'decade'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" default_scale="decade"/>'
            )

    def test_gantt_rejects_unknown_default_range(self):
        with self.assertRaisesRegex(
            ValidationError, "Invalid default_range 'fortnight'"
        ):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" default_range="fortnight"/>'
            )

    def test_gantt_rejects_unknown_display_mode(self):
        with self.assertRaisesRegex(ValidationError, "Invalid display_mode 'chunky'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" display_mode="chunky"/>'
            )

    def test_gantt_rejects_unknown_attribute(self):
        with self.assertRaisesRegex(ValidationError, "Invalid attributes"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" bogus_attr="1"/>'
            )

    def test_dependency_field_requires_its_inverse(self):
        with self.assertRaisesRegex(
            ValidationError, "must have a 'dependency_inverted_field' attribute"
        ):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" dependency_field="parent_id"/>'
            )

    def test_gantt_rejects_child_that_is_not_field_or_templates(self):
        with self.assertRaisesRegex(ValidationError, "got div"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date"><div/></gantt>'
            )

    def test_gantt_rejects_a_second_templates_tag(self):
        with self.assertRaisesRegex(ValidationError, "only one templates tag"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date">'
                "<templates/><templates/>"
                "</gantt>"
            )

    def test_gantt_precision_names_known_scales_and_parts(self):
        self._create_gantt_view(
            '<gantt date_start="create_date" date_stop="write_date"'
            " precision=\"{'day': 'hour:quarter', 'week': 'day:half', 'year': 'month:full'}\"/>"
        )
        with self.assertRaisesRegex(ValidationError, "precision scale 'week_2'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date"'
                " precision=\"{'week_2': 'day:half'}\"/>"
            )
        with self.assertRaisesRegex(ValidationError, "for scale 'week'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date"'
                " precision=\"{'week': 'day:quarter'}\"/>"
            )
        with self.assertRaisesRegex(ValidationError, "expected a dict"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" precision="half"/>'
            )

    def test_gantt_rejects_a_date_bound_that_is_not_a_date_field(self):
        with self.assertRaisesRegex(ValidationError, "not a date field"):
            self._create_gantt_view(
                '<gantt date_start="name" date_stop="write_date" string="Probe"/>'
            )
        with self.assertRaisesRegex(ValidationError, "not a date field"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="" string="Probe"/>'
            )


class TestGanttViewRegistration(TransactionCase):
    def test_gantt_declares_its_client_icon_and_its_date_range(self):
        view = self.env["ir.ui.view"]

        self.assertEqual(
            view._get_view_info()["gantt"],
            {"icon": "fa-solid fa-bars-progress", "date_range": True},
        )
        self.assertTrue(view._view_type_has_date_range("gantt"))

    def test_gantt_is_qweb_based(self):
        view = self.env["ir.ui.view"]

        self.assertTrue(view._is_qweb_based_view("gantt"))
        self.assertFalse(view._is_qweb_based_view("form"))

    def test_gantt_view_fields_request_every_field(self):
        view = self.env["ir.ui.view"]
        view_models = {}

        result = view._get_fields_view("gantt", view_models)

        self.assertEqual(set(result["ir.ui.view"]), set(view._fields))

    def test_non_gantt_view_fields_fall_back_to_base(self):
        view = self.env["ir.ui.view"]

        result = view._get_fields_view("form", {"ir.ui.view": set()})

        self.assertEqual(result["ir.ui.view"], {"id", "write_date"})
