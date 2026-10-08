import logging
import time
from copy import deepcopy
from unittest.mock import patch

import odoo
from odoo.fields import Command
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingSessionCommon,
    TestPoSCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderSyncRetries(PosCashRoundingSessionCommon):
    def test_sync_preserves_payload_for_extensions_and_retries(self):
        order = self._create_bare_order()
        line = self._create_line(order)
        values = self._sync_values(
            order, [[Command.UPDATE, line.id, {"customer_note": "Updated"}]]
        )
        expected = deepcopy(values)

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(line.customer_note, "Updated")
        self.assertEqual(values, expected)
        self.env["pos.order"].sync_from_ui([values])
        self.assertEqual(order.lines, line)

    def test_retry_accepts_immutable_create_commands(self):
        order = self._create_bare_order()
        line = self._create_line(order)
        values = self._sync_values(
            order,
            [Command.create({"uuid": line.uuid, "customer_note": "Retried"})],
        )

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(order.lines, line)
        self.assertEqual(line.customer_note, "Retried")

    def test_fresh_json_retry_does_not_duplicate_records(self):
        order = self._create_bare_order()
        line = self._create_line(order)
        payload = json_dumps(
            self._sync_values(
                order, [[0, 0, {"uuid": line.uuid, "customer_note": "Fresh request"}]]
            )
        )

        for _attempt in range(2):
            self.env["pos.order"].sync_from_ui([json_loads(payload)])

        self.assertEqual(order.lines, line)
        self.assertEqual(line.customer_note, "Fresh request")

    def test_payment_retry_accepts_tuple_commands(self):
        order = self._create_bare_order()
        order.add_payment(
            {
                "pos_order_id": order.id,
                "payment_method_id": self.cash_payment_method.id,
                "amount": 0,
            }
        )
        payment = order.payment_ids
        values = self._sync_values(order, [])
        values["payment_ids"] = [Command.create({"uuid": payment.uuid, "amount": 1})]
        expected = deepcopy(values)

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(order.payment_ids, payment)
        self.assertEqual(payment.amount, 1)
        self.assertEqual(values, expected)


@tagged("post_install", "-at_install")
class TestPosOrderUuidRelations(PosCashRoundingSessionCommon):
    def test_uuid_mapping_links_combo_lines(self):
        order = self._create_bare_order()
        parent = self._create_line(order)
        child = self._create_line(order)
        values = self._sync_values(order, [])
        values["relations_uuid_mapping"] = {
            "pos.order.line": {
                child.uuid: {"combo_parent_id": parent.uuid},
                parent.uuid: {"combo_line_ids": [child.uuid]},
            }
        }

        self.env["pos.order"].sync_from_ui([values])

        self.assertEqual(child.combo_parent_id, parent)
        self.assertEqual(parent.combo_line_ids, child)

    def test_uuid_relations_share_nonempty_comodel_lookup(self):
        order = self._create_bare_order()
        parent, child, grandchild = [self._create_line(order) for _ in range(3)]
        original_search = type(child).search
        searches = []

        def record_search(records, domain, *args, **kwargs):
            searches.append(domain)
            return original_search(records, domain, *args, **kwargs)

        self.env.flush_all()
        before = self.env.cr.sql_statement_count
        with patch.object(type(child), "search", record_search):
            order._link_uuid_relations(
                {
                    "pos.order.line": {
                        child.uuid: {
                            "combo_parent_id": parent.uuid,
                            "combo_line_ids": [grandchild.uuid],
                        }
                    }
                }
            )
        _logger.debug(
            "Nonempty UUID relations: searches=%s SQL statements=%s",
            len(searches),
            self.env.cr.sql_statement_count - before,
        )
        self.assertEqual(child.combo_parent_id, parent)
        self.assertEqual(child.combo_line_ids, grandchild)
        self.assertEqual(grandchild.combo_parent_id, child)
        self.assertEqual(len(searches), 2)

    def test_uuid_relations_preserve_unmapped_and_missing_targets(self):
        order = self._create_bare_order()
        parent = self._create_line(order)
        child = self._create_line(order)
        other = self._create_line(order)
        child.combo_parent_id = parent
        mapping = {
            "pos.order.line": {
                "missing-owner": {"combo_parent_id": parent.uuid},
                child.uuid: {"combo_parent_id": "missing-target"},
                parent.uuid: {"combo_line_ids": [other.uuid, "missing-target"]},
            }
        }

        values = self._sync_values(order, [])
        values["relations_uuid_mapping"] = mapping
        self.env["pos.order"].sync_from_ui([values])

        self.assertFalse(child.combo_parent_id)
        self.assertEqual(parent.combo_line_ids, other)

    def test_uuid_relations_batch_owner_writes(self):
        order = self._create_bare_order()
        parent = self._create_line(order)
        children = self.env["pos.order.line"].create(
            [
                {
                    "order_id": order.id,
                    "product_id": self.product_a.id,
                    "price_subtotal": 0,
                    "price_subtotal_incl": 0,
                }
                for _ in range(20)
            ]
        )
        values = self._sync_values(order, [])
        values["relations_uuid_mapping"] = {
            "pos.order.line": {
                child.uuid: {"combo_parent_id": parent.uuid, "combo_line_ids": []}
                for child in children
            }
        }
        write_batches = []
        uuid_searches = []
        original_write = type(children).write
        original_search = type(children).search

        def record_search(records, domain, *args, **kwargs):
            if len(domain) == 1 and domain[0][0] == "uuid":
                uuid_searches.append(domain)
            return original_search(records, domain, *args, **kwargs)

        def record_write(records, vals):
            if "combo_parent_id" in vals or "combo_line_ids" in vals:
                write_batches.append((records.ids, sorted(vals)))
            return original_write(records, vals)

        started = time.perf_counter()
        statements_before = self.env.cr.sql_statement_count
        with (
            patch.object(type(children), "write", record_write),
            patch.object(type(children), "search", record_search),
        ):
            self.env["pos.order"].sync_from_ui([values])

        _logger.debug(
            "UUID batching: owners=%d writes=%d statements=%d elapsed_ms=%.2f batches=%s",
            len(children),
            len(write_batches),
            self.env.cr.sql_statement_count - statements_before,
            (time.perf_counter() - started) * 1000,
            write_batches,
        )
        self.assertEqual(parent.combo_line_ids, children)
        self.assertLessEqual(len(write_batches), len(children))
        _logger.debug("UUID relation searches: %s", uuid_searches)
        self.assertLessEqual(len(uuid_searches), 2)


@odoo.tests.tagged("post_install", "-at_install")
class TestPosOrderSyncAccessToken(TestPoSCommon):
    def setUp(self):
        super().setUp()
        self.config = self.basic_config

    def _base_order_vals(self, session, uuid, **extra):
        return {
            "uuid": uuid,
            "session_id": session.id,
            "company_id": self.env.company.id,
            "config_id": self.config.id,
            "user_id": self.env.uid,
            "state": "draft",
            "amount_total": 0,
            "amount_tax": 0,
            "amount_paid": 0,
            "amount_return": 0,
            "lines": [],
            "payment_ids": [],
            "date_order": odoo.fields.Datetime.to_string(odoo.fields.Datetime.now()),
            **extra,
        }

    def test_create_path_rejects_client_supplied_access_token(self):
        self.open_new_session()
        uuid = "11111111-1111-4111-8111-111111111111"
        attacker_token = "predictable-token-from-math-random"

        self.env["pos.order"].sync_from_ui(
            [self._base_order_vals(self.pos_session, uuid, access_token=attacker_token)]
        )
        order = self.env["pos.order"].search([("uuid", "=", uuid)])

        self.assertTrue(order, "order was not created")
        self.assertNotEqual(
            order.access_token,
            attacker_token,
            "server persisted a client-supplied access_token",
        )
        self.assertTrue(order.access_token, "server did not mint an access_token")

    def test_update_path_still_rejects_client_supplied_access_token(self):
        self.open_new_session()
        uuid = "22222222-2222-4222-8222-222222222222"

        self.env["pos.order"].sync_from_ui(
            [self._base_order_vals(self.pos_session, uuid)]
        )
        order = self.env["pos.order"].search([("uuid", "=", uuid)])
        minted = order.access_token

        self.env["pos.order"].sync_from_ui(
            [
                self._base_order_vals(
                    self.pos_session,
                    uuid,
                    id=order.id,
                    access_token="second-attempt-token",
                )
            ]
        )
        self.assertEqual(
            self.env["pos.order"].search([("uuid", "=", uuid)]).access_token,
            minted,
            "client rotated the access_token through the update path",
        )
