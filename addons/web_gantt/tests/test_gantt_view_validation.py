from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase


class TestGanttViewValidation(TransactionCase):
    """Cover the arch validation of the gantt view type."""

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
        """Check that a gantt arch with both date bounds is accepted."""
        view = self._create_gantt_view(
            '<gantt date_start="create_date" date_stop="write_date" string="Probe">'
            '<field name="name"/>'
            "</gantt>"
        )

        self.assertEqual(view.type, "gantt")

    def test_single_templates_tag_is_accepted(self):
        """Check that a gantt arch with a single templates tag is accepted."""
        view = self._create_gantt_view(
            '<gantt date_start="create_date" date_stop="write_date"><templates/></gantt>'
        )

        self.assertEqual(view.type, "gantt")

    def test_gantt_requires_date_start(self):
        """Check that a gantt arch without date_start is rejected."""
        # without a start bound the view could not place any pill
        with self.assertRaisesRegex(
            ValidationError, "must have a 'date_start' attribute"
        ):
            self._create_gantt_view('<gantt date_stop="write_date" string="Probe"/>')

    def test_gantt_requires_date_stop(self):
        """Check that a gantt arch without date_stop is rejected."""
        # without a stop bound the view could not size any pill
        with self.assertRaisesRegex(
            ValidationError, "must have a 'date_stop' attribute"
        ):
            self._create_gantt_view('<gantt date_start="create_date" string="Probe"/>')

    def test_gantt_rejects_unknown_default_scale(self):
        """Check that an unknown default_scale value is rejected."""
        with self.assertRaisesRegex(ValidationError, "Invalid default_scale 'decade'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" default_scale="decade"/>'
            )

    def test_gantt_rejects_unknown_default_range(self):
        """Check that an unknown default_range value is rejected."""
        with self.assertRaisesRegex(
            ValidationError, "Invalid default_range 'fortnight'"
        ):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" default_range="fortnight"/>'
            )

    def test_gantt_rejects_unknown_display_mode(self):
        """Check that a display_mode other than dense or sparse is rejected."""
        with self.assertRaisesRegex(ValidationError, "Invalid display_mode 'chunky'"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" display_mode="chunky"/>'
            )

    def test_gantt_rejects_unknown_attribute(self):
        """Check that an attribute outside the whitelist is rejected."""
        with self.assertRaisesRegex(ValidationError, "Invalid attributes"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" bogus_attr="1"/>'
            )

    def test_dependency_field_requires_its_inverse(self):
        """Check that dependency_field without its inverse is rejected."""
        with self.assertRaisesRegex(
            ValidationError, "must have a 'dependency_inverted_field' attribute"
        ):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date" dependency_field="parent_id"/>'
            )

    def test_gantt_rejects_child_that_is_not_field_or_templates(self):
        """Check that a child tag other than field or templates is rejected."""
        with self.assertRaisesRegex(ValidationError, "got div"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date"><div/></gantt>'
            )

    def test_gantt_rejects_a_second_templates_tag(self):
        """Check that a gantt arch with two templates tags is rejected."""
        with self.assertRaisesRegex(ValidationError, "only one templates tag"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="write_date">'
                "<templates/><templates/>"
                "</gantt>"
            )

    def test_gantt_precision_names_known_scales_and_parts(self):
        """Check that a precision key or part the client would drop is refused."""
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
        """Check that a date bound must name a date or datetime field."""
        with self.assertRaisesRegex(ValidationError, "not a date field"):
            self._create_gantt_view(
                '<gantt date_start="name" date_stop="write_date" string="Probe"/>'
            )
        with self.assertRaisesRegex(ValidationError, "not a date field"):
            self._create_gantt_view(
                '<gantt date_start="create_date" date_stop="" string="Probe"/>'
            )


class TestGanttViewRegistration(TransactionCase):
    """Cover how the gantt type registers itself against ir.ui.view."""

    def test_gantt_declares_its_client_icon_and_its_date_range(self):
        """Check that the gantt view type declares its switcher icon, and that
        its arch bounds the records a listing shows by date -- what the /json
        route reads instead of naming the type in a literal."""
        view = self.env["ir.ui.view"]

        self.assertEqual(
            view._get_view_info()["gantt"],
            {"icon": "fa-solid fa-bars-progress", "date_range": True},
        )
        self.assertTrue(view._view_type_has_date_range("gantt"))

    def test_gantt_is_qweb_based(self):
        """Check that gantt is reported as qweb-based and form is not."""
        view = self.env["ir.ui.view"]

        self.assertTrue(view._is_qweb_based_view("gantt"))
        self.assertFalse(view._is_qweb_based_view("form"))

    def test_gantt_view_fields_request_every_field(self):
        """Check that the gantt view type requests every model field."""
        view = self.env["ir.ui.view"]
        view_models = {}

        result = view._get_fields_view("gantt", view_models)

        self.assertEqual(set(result["ir.ui.view"]), set(view._fields))

    def test_non_gantt_view_fields_fall_back_to_base(self):
        """Check that non-gantt view types keep the base field resolution."""
        view = self.env["ir.ui.view"]

        result = view._get_fields_view("form", {"ir.ui.view": set()})

        self.assertEqual(result["ir.ui.view"], {"id", "write_date"})
