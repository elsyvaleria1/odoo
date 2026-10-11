from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@tagged("post_install", "-at_install")
class TestPosPrepState(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config
        cls.display = cls.env["pos.prep.display"].create({"name": "Kitchen Display"})
        cls.stages = cls.display.stage_ids.sorted("id")
        cls.product = cls.env["product.product"].create(
            {"name": "Prep Burger", "available_in_pos": True, "list_price": 10.0}
        )

    def _make_prep_state(self, stage):
        self.config.open_ui()
        session = self.config.current_session_id
        order = self.env["pos.order"].create(
            {
                "company_id": self.env.company.id,
                "session_id": session.id,
                "lines": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "qty": 1,
                            "price_unit": 10.0,
                            "price_subtotal": 10.0,
                            "price_subtotal_incl": 10.0,
                        }
                    )
                ],
                "amount_tax": 0.0,
                "amount_total": 10.0,
                "amount_paid": 0.0,
                "amount_return": 0.0,
            }
        )
        prep_order = self.env["pos.prep.order"].create(
            {
                "pos_order_id": order.id,
                "prep_line_ids": [
                    Command.create(
                        {
                            "quantity": 1,
                            "pos_order_line_id": order.lines[0].id,
                        }
                    )
                ],
            }
        )
        state = self.env["pos.prep.state"].create(
            {
                "prep_line_id": prep_order.prep_line_ids[0].id,
                "stage_id": stage.id,
            }
        )
        return order.lines[0], prep_order, state

    def test_order_line_time_sentinels_default(self):
        pos_line, _prep_order, _state = self._make_prep_state(self.stages[0])
        self.assertEqual(pos_line.preparation_time, -1)
        self.assertEqual(pos_line.service_time, -1)

    def test_change_state_status_records_and_resets_preparation_time(self):
        pos_line, _prep_order, state = self._make_prep_state(self.stages[0])

        state.change_state_status({str(state.id): False}, str(self.display.id))
        self.assertFalse(state.todo)
        self.assertGreaterEqual(pos_line.preparation_time, 0)

        state.change_state_status({str(state.id): True}, str(self.display.id))
        self.assertTrue(state.todo)
        self.assertEqual(pos_line.preparation_time, -1)


    def test_display_without_stages_is_refused(self):
        with self.assertRaisesRegex(ValidationError, "minimum of one step"):
            self.display.stage_ids = [Command.clear()]

    def test_change_state_stage_to_last_records_service_and_completion(self):
        pos_line, prep_order, state = self._make_prep_state(self.stages[0])

        state.change_state_stage(
            {str(state.id): self.stages[-1].id}, str(self.display.id)
        )
        self.assertEqual(state.stage_id, self.stages[-1])
        self.assertTrue(state.todo)
        self.assertGreaterEqual(pos_line.service_time, 0)
        self.assertGreaterEqual(prep_order.completion_time, 0)
