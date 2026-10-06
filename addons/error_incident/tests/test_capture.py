from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.error_incident.models.error_incident import capture_payload
from odoo.addons.error_incident.models.error_occurrence import (
    KEPT_PER_INCIDENT_PARAM,
)


def _fail(message="the defect"):
    raise ValueError(message)


def _payload(source="request", message="the defect", **kwargs):
    try:
        _fail(message)
    except ValueError as exc:
        return capture_payload(exc, source, **kwargs)
    raise AssertionError


@tagged("post_install", "-at_install")
class TestCapture(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Incident = cls.env["error.incident"]
        cls.user = cls.env["res.users"].create(
            {"name": "Incident User", "login": "incident.user@example.com"}
        )
        cls.other = cls.env["res.users"].create(
            {"name": "Incident Other", "login": "incident.other@example.com"}
        )

    def _capture(self, **kwargs):
        return self.Incident.browse(self.Incident._capture(_payload(**kwargs)))

    def test_occurrences_of_one_defect_are_one_incident(self):
        first = self._capture()
        second = self._capture(source="cron")
        self.assertEqual(first, second)
        self.assertEqual(first.count_occurrence, 2)
        self.assertEqual(len(first.occurrence_ids), 2)
        self.assertEqual(first.source, "request", "the first source is kept")
        self.assertEqual(first.incident_state, "new")
        self.assertEqual(first.origin_function, "_fail")

    def test_a_burst_is_one_incident_and_a_count(self):
        payload = _payload()
        for _ in range(1000):
            incident_id = self.Incident._capture(
                dict(payload, occurrence_ref=None) | {"occurrence_ref": f"k{_}"}
            )
        incident = self.Incident.browse(incident_id)
        self.assertEqual(self.Incident.search_count([]), 1)
        self.assertEqual(incident.count_occurrence, 1000)

    def test_everyone_who_hit_it_is_known(self):
        incident = self._capture(user_id=self.user.id)
        self._capture(user_id=self.user.id)
        self._capture(user_id=self.other.id)
        self.assertEqual(incident.user_ids, self.user | self.other)

    def test_a_resolved_incident_that_recurs_is_a_regression(self):
        incident = self._capture()
        incident.action_resolve()
        self._capture()
        self.assertEqual(incident.incident_state, "regressed")
        self.assertEqual(incident.count_regression, 1)
        self.assertIn("occurred again", incident.message_ids[0].body)
        self._capture()
        self.assertEqual(incident.count_regression, 1, "regressed once, not twice")

    def test_a_rule_sets_a_new_incident_aside(self):
        rule = self.env["error.incident.rule"].create(
            {"name": "crons", "source": "cron", "exception_type": "ValueError"}
        )
        incident = self._capture(source="cron")
        self.assertEqual(incident.incident_state, "set_aside")
        self.assertEqual(incident.rule_id, rule)
        self.assertEqual(incident.count_occurrence, 1, "still counted")

    def test_secrets_are_masked_before_storage(self):
        incident = self._capture(message="login failed password=hunter2 for x")
        occurrence = incident.occurrence_ids
        self.assertNotIn("hunter2", occurrence.message)
        self.assertNotIn("hunter2", occurrence.traceback)

    def test_recording_never_raises_on_the_error_path(self):
        with patch.object(
            type(self.Incident), "_capture", side_effect=RuntimeError("db gone")
        ):
            self.assertIsNone(self.Incident._capture_quietly(_payload()))
        self.env.cr.execute("SELECT 1")

    def test_old_occurrences_are_forgotten_and_each_incident_keeps_its_newest(self):
        incident = self._capture()
        for _ in range(4):
            self._capture()
        self.env["ir.config_parameter"].sudo().set_param(KEPT_PER_INCIDENT_PARAM, "3")
        oldest = incident.occurrence_ids.sorted("id")[0]
        self.env["error.occurrence"]._gc_occurrences()
        self.assertEqual(len(incident.occurrence_ids), 3)
        self.assertFalse(oldest.exists())
        self.assertEqual(incident.count_occurrence, 5, "the count is history")

        recent = incident.occurrence_ids[0]
        recent.date_occurred = fields.Datetime.now() - timedelta(days=400)
        self.env["error.occurrence"]._gc_occurrences()
        self.assertFalse(recent.exists())
