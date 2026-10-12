from dateutil.relativedelta import relativedelta

from odoo.fields import Command, Datetime
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "data_cleaning")
class TestCleaningNotification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = cls.env.ref("base.user_admin")
        cls.admin.email = "mitchell.admin@example.com"
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        name_field = cls.env["ir.model.fields"].search(
            [("name", "=", "name"), ("model_id", "=", cls.partner_model.id)], limit=1
        )

        cls.cleaning_model = cls.env["data_cleaning.model"].create(
            {
                "name": "Trim partner names",
                "res_model_id": cls.partner_model.id,
                "cleaning_mode": "manual",
                "notify_user_ids": [(6, 0, cls.admin.ids)],
                "notify_interval": 1,
                "notify_unit": "week",
                "rule_ids": [
                    (0, 0, {"field_id": name_field.id, "action": "trim", "sequence": 1})
                ],
            }
        )
        cls.env["res.partner"].create({"name": "  padded  "})

    def _count_notifications(self):
        return self.env["mail.notification"].search_count([])

    def test_a_silent_run_does_not_consume_the_period(self):
        self.cleaning_model._notify_pending_records()
        self.assertFalse(
            self.cleaning_model.last_notification,
            "nothing was queued, so nothing was sent and the period is not spent",
        )

        self.cleaning_model._clean_records()
        self.assertTrue(self.cleaning_model.records_to_clean_count)
        before = self._count_notifications()
        self.cleaning_model._notify_pending_records()
        self.assertEqual(self._count_notifications(), before + 1)
        self.assertTrue(self.cleaning_model.last_notification)

    def test_the_period_is_then_respected(self):
        self.cleaning_model._clean_records()
        self.cleaning_model._notify_pending_records()
        before = self._count_notifications()

        self.cleaning_model._notify_pending_records()
        self.assertEqual(self._count_notifications(), before, "still inside the period")

        self.cleaning_model.last_notification = Datetime.now() - relativedelta(weeks=2)
        self.cleaning_model._notify_pending_records()
        self.assertEqual(self._count_notifications(), before + 1)

    def test_a_day_period_counts_days(self):
        self.cleaning_model.write(
            {
                "notify_unit": "day",
                "notify_interval": 5,
            }
        )
        self.cleaning_model._clean_records()
        self.cleaning_model._notify_pending_records()
        before = self._count_notifications()

        self.cleaning_model.last_notification = Datetime.now() - relativedelta(days=2)
        self.cleaning_model._notify_pending_records()
        self.assertEqual(
            self._count_notifications(),
            before,
            "two days into a five-day period, nothing is due",
        )

        self.cleaning_model.last_notification = Datetime.now() - relativedelta(days=6)
        self.cleaning_model._notify_pending_records()
        self.assertEqual(self._count_notifications(), before + 1)

    def test_the_backlog_is_counted_whole(self):
        self.cleaning_model._clean_records()
        self.env["data_cleaning.record"].search(
            [("cleaning_model_id", "=", self.cleaning_model.id)]
        ).write({"create_date": Datetime.now() - relativedelta(years=1)})
        self.assertTrue(
            self.cleaning_model._send_notification(),
            "a backlog older than one period is still a backlog",
        )

    def test_an_automatic_rule_notifies_nobody(self):
        self.cleaning_model.cleaning_mode = "automatic"
        self.cleaning_model._clean_records()
        before = self._count_notifications()
        self.cleaning_model._notify_pending_records()
        self.assertEqual(self._count_notifications(), before)

    def test_archiving_a_rule_clears_its_discarded_records(self):
        self.cleaning_model._clean_records()
        records = self.env["data_cleaning.record"].search(
            [("cleaning_model_id", "=", self.cleaning_model.id)]
        )
        self.assertTrue(records)
        records[0].action_discard()
        self.cleaning_model.active = False
        self.assertFalse(
            self.env["data_cleaning.record"]
            .with_context(active_test=False)
            .search([("cleaning_model_id", "=", self.cleaning_model.id)]),
            "a discarded record must not outlive the rule that produced it",
        )


@tagged("post_install", "-at_install", "data_cleaning")
class TestMergeNotification(TransactionCase):
    def test_a_merge_rule_keeps_its_empty_notify_default(self):
        merge_default = self.env["data_merge.model"].default_get(["notify_user_ids"])
        recycle_default = self.env["data_recycle.model"].default_get(
            ["notify_user_ids"]
        )
        self.assertEqual(merge_default["notify_user_ids"], [Command.set([])])
        self.assertEqual(
            recycle_default["notify_user_ids"],
            [Command.set(self.env.user.ids)],
            "the mixin's own default, still in force where it was already the behaviour",
        )
        self.assertEqual(
            self.env["data_merge.model"].default_get(["notify_unit"])["notify_unit"],
            "week",
        )

    def test_a_day_period_counts_days(self):
        merge_model = self.env["data_merge.model"].create(
            {
                "name": "Dedup partners by day",
                "res_model_id": self.env["ir.model"]._get("res.partner").id,
                "merge_mode": "manual",
                "notify_unit": "day",
                "notify_interval": 5,
                "notify_user_ids": [(6, 0, self.env.ref("base.user_admin").ids)],
            }
        )
        merge_model.last_notification = Datetime.now() - relativedelta(days=2)
        before = self.env["mail.notification"].search_count([])
        merge_model._notify_pending_records()
        self.assertEqual(
            self.env["mail.notification"].search_count([]),
            before,
            "two days into a five-day period, nothing is due -- `relativedelta(day=5)` "
            "made this come due on every run",
        )
