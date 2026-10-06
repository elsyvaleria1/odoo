from unittest.mock import patch

from odoo.tests import TransactionCase


class TestDefaultGanttView(TransactionCase):
    def test_default_view_names_the_declared_date_fields(self):
        view = self.env["test.web.gantt.pill"]._get_default_gantt_view()
        self.assertEqual(view.get("date_start"), "date_start")
        self.assertEqual(view.get("date_stop"), "date_stop")

    def test_default_view_infers_alternative_date_field_names(self):
        model = self.env["test.web.gantt.pill"]
        fields = {
            "start_date": model._fields["date_start"],
            "date_end": model._fields["date_stop"],
        }
        with patch.object(type(model), "_fields", fields):
            view = model._get_default_gantt_view()
        self.assertEqual(view.get("date_start"), "start_date")
        self.assertEqual(view.get("date_stop"), "date_end")

    def test_gantt_view_sends_every_field_of_the_model(self):
        views = self.env["test.web.gantt.pill"].get_views([(False, "gantt")])
        self.assertIn("parent_id", views["models"]["test.web.gantt.pill"]["fields"])
