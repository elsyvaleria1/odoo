from odoo import Command
from odoo.fields import Domain
from odoo.tests import TransactionCase, tagged

from odoo.addons.quality_mrp_workorder.models.product import (
    _update_quality_point_action,
)


@tagged("post_install", "-at_install")
class TestQualityPointAction(TransactionCase):
    def test_updates_existing_action_in_place(self):
        context = {"keep": "value", "search_default_quality_points": 0}
        original_domain = [("id", "in", [1, 2])]
        action = {"context": context, "domain": original_domain, "name": "Keep"}
        self.assertIsNone(_update_quality_point_action(action))
        self.assertIs(action["context"], context)
        self.assertEqual(context, {"keep": "value", "search_default_quality_points": 1})
        self.assertEqual(action["name"], "Keep")
        self.assertEqual(original_domain, [("id", "in", [1, 2])])
        self.assertEqual(
            action["domain"],
            Domain.AND(
                [
                    original_domain,
                    [
                        "|",
                        "|",
                        ("operation_id", "=", False),
                        ("bom_id", "=", False),
                        ("bom_active", "=", True),
                    ],
                ]
            ),
        )

    def test_requires_parent_action_fields(self):
        with self.assertRaises(KeyError):
            _update_quality_point_action({"domain": []})
        context = {}
        with self.assertRaises(KeyError):
            _update_quality_point_action({"context": context})
        self.assertEqual(context, {"search_default_quality_points": 1})

    def test_template_and_variant_exclude_archived_operation_points(self):
        product = self.env["product.product"].create({"name": "Action product"})
        other = self.env["product.product"].create({"name": "Other action product"})
        workcenter = self.env["mrp.workcenter"].create({"name": "Action workcenter"})
        bom = self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "operation_ids": [
                    Command.create({"name": "Inspect", "workcenter_id": workcenter.id})
                ],
            }
        )
        point = self.env["quality.point"].create(
            {
                "title": "Operation point",
                "product_ids": [Command.set(product.ids)],
                "picking_type_ids": [
                    Command.set(self.env.ref("stock.warehouse0").manu_type_id.ids)
                ],
                "bom_id": bom.id,
                "operation_id": bom.operation_ids.id,
            }
        )
        general = point.copy(
            {"title": "General point", "operation_id": False, "bom_id": False}
        )
        unrelated = general.copy({"product_ids": [Command.set(other.ids)]})
        for active in (True, False):
            bom.active = active
            for record in (product.product_tmpl_id, product):
                with self.subTest(active=active, model=record._name):
                    action = record.with_context(
                        action_marker="keep"
                    ).action_view_quality_control_points()
                    matches = self.env["quality.point"].search(action["domain"])
                    self.assertEqual(point in matches, active)
                    self.assertIn(general, matches)
                    self.assertNotIn(unrelated, matches)
                    self.assertEqual(action["context"]["action_marker"], "keep")
                    self.assertEqual(
                        action["context"]["search_default_quality_points"], 1
                    )
                    self.assertEqual(
                        action["context"]["default_product_ids"], product.ids
                    )
