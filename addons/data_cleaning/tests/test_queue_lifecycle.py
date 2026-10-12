from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install", "data_cleaning")
class TestQueueRetarget(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner_model = cls.env["ir.model"]._get("res.partner")
        cls.bank_model = cls.env["ir.model"]._get("res.bank")
        cls.partner_name = cls.env["ir.model.fields"].search(
            [("name", "=", "name"), ("model_id", "=", cls.partner_model.id)], limit=1
        )

    def test_a_cleaning_rule_drops_its_queue_when_its_model_changes(self):
        self.env["res.partner"].create({"name": "  padded  "})
        cleaning_model = self.env["data_cleaning.model"].create(
            {
                "name": "trim partners",
                "res_model_id": self.partner_model.id,
                "cleaning_mode": "manual",
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "field_id": self.partner_name.id,
                            "action": "trim",
                            "sequence": 1,
                        },
                    )
                ],
            }
        )
        cleaning_model._clean_records()
        queued = self.env["data_cleaning.record"].search(
            [("cleaning_model_id", "=", cleaning_model.id)]
        )
        self.assertTrue(
            queued, "something must be queued for the test to mean anything"
        )
        partner_res_ids = sorted(queued.mapped("res_id"))

        cleaning_model.res_model_id = self.bank_model
        self.assertFalse(
            self.env["data_cleaning.record"]
            .with_context(active_test=False)
            .search([("cleaning_model_id", "=", cleaning_model.id)]),
            "res_ids %s belonged to res.partner and name different res.bank records"
            % partner_res_ids,
        )

    def test_a_cleaning_rule_keeps_its_queue_on_an_unrelated_write(self):
        self.env["res.partner"].create({"name": "  padded  "})
        cleaning_model = self.env["data_cleaning.model"].create(
            {
                "name": "trim partners",
                "res_model_id": self.partner_model.id,
                "cleaning_mode": "manual",
                "rule_ids": [
                    (
                        0,
                        0,
                        {
                            "field_id": self.partner_name.id,
                            "action": "trim",
                            "sequence": 1,
                        },
                    )
                ],
            }
        )
        cleaning_model._clean_records()
        before = self.env["data_cleaning.record"].search(
            [("cleaning_model_id", "=", cleaning_model.id)]
        )
        self.assertTrue(before)

        cleaning_model.write({"name": "renamed", "res_model_id": self.partner_model.id})
        self.assertEqual(
            self.env["data_cleaning.record"].search(
                [("cleaning_model_id", "=", cleaning_model.id)]
            ),
            before,
            "the model did not actually change, so the queue must survive",
        )

    def test_a_merge_rule_drops_its_groups_when_its_model_changes(self):
        self.env["res.partner"].create([{"name": "Twin"}, {"name": "Twin"}])
        merge_model = self.env["data_merge.model"].create(
            {
                "name": "dedup partners",
                "res_model_id": self.partner_model.id,
                "merge_mode": "manual",
            }
        )
        self.env["data_merge.rule"].create(
            {
                "model_id": merge_model.id,
                "field_id": self.partner_name.id,
                "match_mode": "exact",
            }
        )
        merge_model.find_duplicates()
        groups = self.env["data_merge.group"].search(
            [("model_id", "=", merge_model.id)]
        )
        self.assertTrue(
            groups, "a duplicate group must exist for the test to mean anything"
        )

        merge_model.res_model_id = self.bank_model
        self.assertFalse(
            self.env["data_merge.group"]
            .with_context(active_test=False)
            .search([("model_id", "=", merge_model.id)]),
            "the groups held res.partner ids and would have merged res.bank records",
        )
        self.assertFalse(
            self.env["data_merge.record"]
            .with_context(data_merge_model_ids=tuple(merge_model.ids))
            .search([("model_id", "=", merge_model.id)]),
            "and their records go with them",
        )
