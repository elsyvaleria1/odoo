from lxml import etree

from odoo.tests.common import TransactionCase


class TestViewAnchors(TransactionCase):

    def _combined(self, xml_id):
        return etree.fromstring(self.env.ref(xml_id).get_combined_arch())

    def test_the_operator_filters_sit_before_the_service_filters(self):
        arch = self._combined("resource_asset_vehicle.fleet_vehicle_view_search")

        names = [node.get("name") for node in arch if node.tag == "filter"]

        self.assertLess(
            names.index("has_operator"),
            names.index("service_overdue"),
            "The HR filters come ahead of Service Overdue.",
        )

    def test_the_kanban_operator_lands_in_the_header_block(self):
        arch = self._combined("asset_ledger.view_kanban_product_asset_log")

        holders = [
            node.getparent()
            for node in arch.iter("field")
            if node.get("name") == "operator_id"
        ]

        self.assertEqual(len(holders), 1)
        self.assertEqual(holders[0].get("class"), "col-12 pe-2 text-truncate")
        self.assertEqual(holders[0].getparent().get("class"), "flex-row")

    def test_the_kanban_names_the_operator_inside_the_card(self):
        arch = self._combined("asset_ledger.resource_asset_view_kanban_fleet")

        holders = [
            node
            for node in arch.iter("field")
            if node.get("name") == "operator_employee_id"
        ]

        self.assertTrue(holders, "the vehicle kanban names its operator")

    def test_the_operator_family_shares_one_asset_kind_predicate(self):
        arch = self._combined("asset_ledger.resource_asset_view_form_ledger")
        names = (
            "operator_employee_id",
            "future_operator_employee_id",
            "action_accept_operator_change",
            "action_view_logs_assignation",
        )

        predicates = {
            node.get("name"): node.get("invisible")
            for node in arch.iter("field", "button")
            if node.get("name") in names
        }

        self.assertEqual(sorted(predicates), sorted(names))
        self.assertEqual(
            {name: value for name, value in predicates.items() if value},
            {"action_accept_operator_change": "not future_operator_employee_id"},
            "Only the Accept button hides, and on the successor, not the kind.",
        )
