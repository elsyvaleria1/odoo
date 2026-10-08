import logging
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import CommonPosTest, TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosRobustness(CommonPosTest):
    def setUp(self):
        super().setUp()
        self.pos_config_usd.open_ui()
        self.session = self.pos_config_usd.current_session_id
        self.product = self.env["product.product"].search(
            [("available_in_pos", "=", True)], limit=1
        )

    def _order(self, **vals):
        return self.env["pos.order"].create(
            {
                "session_id": self.session.id,
                "amount_tax": 0,
                "amount_total": 0,
                "amount_paid": 0,
                "amount_return": 0,
                **vals,
            }
        )

    def test_config_write_leaves_the_caller_dict_alone(self):
        vals = {"is_order_printer": False}
        self.pos_config_usd.write(vals)
        self.assertEqual(vals, {"is_order_printer": False})

    def test_config_write_does_not_leak_between_records(self):
        printer = self.env["pos.printer"].create(
            {"name": "Kitchen", "proxy_ip": "10.0.0.1"}
        )
        for config in (self.pos_config_usd, self.pos_config_eur):
            config.write(
                {"is_order_printer": True, "printer_ids": [Command.link(printer.id)]}
            )
        vals = {"iface_big_scrollbars": True}
        self.pos_config_usd.write(vals)
        self.pos_config_eur.write(vals)
        self.assertIn(printer, self.pos_config_eur.printer_ids)

    def test_order_create_leaves_the_caller_dict_alone(self):
        vals = {
            "session_id": self.session.id,
            "amount_tax": 0,
            "amount_total": 0,
            "amount_paid": 0,
            "amount_return": 0,
        }
        expected = dict(vals)
        self.env["pos.order"].create(vals)
        self.assertEqual(vals, expected)

    def test_order_without_a_session_is_refused_by_name(self):
        with self.assertRaises(UserError):
            self.env["pos.order"].create({"amount_tax": 0, "amount_total": 0})

    def test_config_sequences_have_distinct_codes(self):
        config = self.pos_config_usd
        codes = [
            config.order_seq_id.code,
            config.order_backend_seq_id.code,
            config.order_line_seq_id.code,
            config.device_seq_id.code,
        ]
        self.assertEqual(len(set(codes)), 4, codes)

    def test_order_line_without_a_sequence_names_the_problem(self):
        order = self._order()
        self.pos_config_usd.sudo().order_line_seq_id = False
        with self.assertRaises(UserError):
            self.env["pos.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": 0,
                    "price_subtotal": 0,
                    "price_subtotal_incl": 0,
                }
            )

    def test_filter_local_data_on_a_model_without_active(self):
        order = self._order()
        self.assertNotIn("active", self.env["pos.order"]._fields)
        result = self.session.filter_local_data({"pos.order": [order.id]})
        self.assertEqual(result["pos.order"], [])

    def test_filter_local_data_reports_deleted_records(self):
        order = self._order()
        order_id = order.id
        order.unlink()
        result = self.session.filter_local_data({"pos.order": [order_id]})
        self.assertEqual(result["pos.order"], [order_id])

    def test_filter_local_data_reports_archived_records(self):
        template = self.env["product.template"].create({"name": "Archived probe"})
        template.active = False
        result = self.session.filter_local_data({"product.template": [template.id]})
        self.assertEqual(result["product.template"], [template.id])

    def test_total_cost_survives_a_zero_quantity_refunded_line(self):
        order = self._order(shipping_date=fields.Date.today())
        zero_line = self.env["pos.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "qty": 0,
                "price_unit": 0,
                "price_subtotal": 0,
                "price_subtotal_incl": 0,
                "total_cost": 0,
            }
        )
        refund_line = self.env["pos.order.line"].create(
            {
                "order_id": order.id,
                "product_id": self.product.id,
                "qty": -1,
                "price_unit": 0,
                "price_subtotal": 0,
                "price_subtotal_incl": 0,
                "refunded_orderline_id": zero_line.id,
            }
        )
        refund_line._update_total_cost(self.env["stock.move"])
        self.assertTrue(refund_line.is_total_cost_computed)

    def test_printed_order_refuses_a_new_payment(self):
        cash_pm = self.session.payment_method_ids.filtered("is_cash_count")[:1]
        order = self._order(state="paid", nb_print=1)
        with self.assertRaises(UserError):
            order.write(
                {
                    "payment_ids": [
                        Command.create(
                            {
                                "payment_method_id": cash_pm.id,
                                "amount": 5,
                                "payment_status": "done",
                            }
                        )
                    ]
                }
            )
        self.assertFalse(order.payment_ids)

    def test_preparation_change_is_single_record(self):
        first = self._order()
        second = self._order()
        with self.assertRaises(ValueError):
            (first | second)._keep_newest_preparation_change({})

    def test_preparation_change_keeps_the_newer_payload(self):
        order = self._order()
        order.last_order_preparation_change = json_dumps(
            {"metadata": {"serverDate": "2030-01-01 00:00:00"}}
        )
        vals = {
            "last_order_preparation_change": json_dumps(
                {"metadata": {"serverDate": "2020-01-01 00:00:00"}}
            )
        }
        order._keep_newest_preparation_change(vals)
        self.assertEqual(
            json_loads(vals["last_order_preparation_change"])["metadata"]["serverDate"],
            "2030-01-01 00:00:00",
        )

    def test_deleting_lines_posts_one_message(self):
        self.pos_config_usd.order_edit_tracking = True
        order = self._order()
        for _i in range(3):
            self.env["pos.order.line"].create(
                {
                    "order_id": order.id,
                    "product_id": self.product.id,
                    "qty": 1,
                    "price_unit": 0,
                    "price_subtotal": 0,
                    "price_subtotal_incl": 0,
                }
            )
        before = len(order.message_ids)
        order.lines.unlink()
        self.assertEqual(len(order.message_ids) - before, 1)
        self.assertTrue(order.has_deleted_line)

    def test_read_pos_data_without_a_config(self):
        order = self._order()
        with_config = order.read_pos_data([], self.pos_config_usd)
        without_config = order.read_pos_data([], False)
        self.assertEqual(set(with_config), set(without_config))
        self.assertTrue(all(value == [] for value in without_config.values()))

    def _spy_read_pos_data(self):
        PosOrder = type(self.env["pos.order"])
        read_pos_data = PosOrder.read_pos_data
        reads = []

        def spy(orders, data, config):
            reads.append((orders.config_id, config))
            return read_pos_data(orders, data, config)

        return patch.object(PosOrder, "read_pos_data", spy), reads

    def _line_vals(self, qty, **vals):
        return {
            "product_id": self.product.id,
            "qty": qty,
            "price_unit": 0,
            "price_subtotal": 0,
            "price_subtotal_incl": 0,
            **vals,
        }

    def test_orders_of_two_configs_are_each_read_with_their_own_config(self):
        self.pos_config_eur.open_ui()
        eur_order = self._order(session_id=self.pos_config_eur.current_session_id.id)
        usd_order = self._order()
        spying, reads = self._spy_read_pos_data()
        with spying:
            result = self.env["pos.order"].read_pos_orders(
                [("id", "in", (usd_order | eur_order).ids)]
            )
        self.assertCountEqual(
            reads,
            [
                (self.pos_config_usd, self.pos_config_usd),
                (self.pos_config_eur, self.pos_config_eur),
            ],
        )
        self.assertCountEqual(
            [row["id"] for row in result["pos.order"]], (usd_order | eur_order).ids
        )

    def test_a_refund_synced_on_another_config_reads_each_order_with_its_config(self):
        sold = self._order(lines=[Command.create(self._line_vals(1))])
        self.pos_config_eur.open_ui()
        refund_uuid = "11111111-2222-4333-8444-555555555555"
        spying, reads = self._spy_read_pos_data()
        with spying:
            result = self.env["pos.order"].sync_from_ui(
                [
                    {
                        "uuid": refund_uuid,
                        "session_id": self.pos_config_eur.current_session_id.id,
                        "state": "draft",
                        "amount_tax": 0,
                        "amount_total": 0,
                        "amount_paid": 0,
                        "amount_return": 0,
                        "last_order_preparation_change": "{}",
                        "lines": [
                            Command.create(
                                self._line_vals(-1, refunded_orderline_id=sold.lines.id)
                            )
                        ],
                    }
                ]
            )
        self.assertCountEqual(
            reads,
            [
                (self.pos_config_usd, self.pos_config_usd),
                (self.pos_config_eur, self.pos_config_eur),
            ],
        )
        self.assertCountEqual(
            [row["uuid"] for row in result["pos.order"]], [sold.uuid, refund_uuid]
        )
        self.assertEqual(
            [row["id"] for row in result["pos.order.line"]].count(sold.lines.id), 1
        )

    def test_is_vat_follows_the_config_company(self):
        config = self.pos_config_usd
        config.company_id.country_id = self.env.ref("base.be")
        payload = config._load_pos_data_read(config, config)
        self.assertTrue(payload[0]["_IS_VAT"])
        config.company_id.country_id = self.env.ref("base.us")
        payload = config._load_pos_data_read(config, config)
        self.assertFalse(payload[0]["_IS_VAT"])


@tagged("post_install", "-at_install")
class TestPosOrderBatchWrite(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.product = self.create_product(
            "Batch write product", self.categ_basic, 100, 50
        )

    def test_a_batch_write_sets_has_deleted_line_on_every_order(self):
        self._start_pos_session(self.cash_pm1, 0)
        orders_map = self._create_orders(
            [
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "audit-r3-a",
                },
                {
                    "pos_order_lines_ui_args": [(self.product, 1)],
                    "payments": [(self.cash_pm1, 100)],
                    "uuid": "audit-r3-b",
                },
            ]
        )
        order_a = orders_map["audit-r3-a"]
        order_b = orders_map["audit-r3-b"]
        order_a.has_deleted_line = False
        order_b.has_deleted_line = True
        (order_a | order_b).write({"has_deleted_line": True})
        _logger.info(
            "has_deleted_line a=%s b=%s",
            order_a.has_deleted_line,
            order_b.has_deleted_line,
        )
        self.assertTrue(
            order_a.has_deleted_line,
            "batch write dropped has_deleted_line for order A "
            "because a sibling order mutated the shared vals dict",
        )
        self.assertTrue(order_b.has_deleted_line)
