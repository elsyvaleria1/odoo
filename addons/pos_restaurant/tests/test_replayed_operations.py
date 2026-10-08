from uuid import uuid4

from odoo.tests import tagged

from odoo.addons.pos_restaurant.tests.test_frontend import TestFrontendCommon


@tagged("post_install", "-at_install")
class TestReplayedRestaurantOperations(TestFrontendCommon):
    def setUp(self):
        super().setUp()
        self.authenticate("pos_admin", "pos_admin")

    def _create(self, model, values, operation):
        return self.call_jsonrpc(
            f"/web/dataset/call_kw/{model}/create",
            {
                "model": model,
                "method": "create",
                "args": [[values]],
                "kwargs": {"context": {"pos_operation_uuid": operation}},
            },
        )

    def test_a_replayed_table_create_connects_the_first_table(self):
        operation = str(uuid4())
        values = {
            "table_number": 99,
            "floor_id": self.main_floor.id,
            "seats": 4,
            "active": True,
        }

        first = self._create("restaurant.table", values, operation)
        second = self._create("restaurant.table", values, operation)

        self.assertEqual(first, second)
        self.assertEqual(
            self.env["restaurant.table"]
            .search([("floor_id", "=", self.main_floor.id), ("table_number", "=", 99)])
            .ids,
            first,
        )

    def test_a_replayed_floor_create_connects_the_first_floor(self):
        operation = str(uuid4())
        values = {
            "name": "Terrace",
            "background_color": "white",
            "pos_config_ids": [self.pos_config.id],
        }

        first = self._create("restaurant.floor", values, operation)
        second = self._create("restaurant.floor", values, operation)

        self.assertEqual(first, second)
        self.assertEqual(
            self.env["restaurant.floor"].search([("name", "=", "Terrace")]).ids, first
        )
