import logging
from copy import deepcopy

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import (
    PosCashRoundingSessionCommon,
    PosOpenSessionCommon,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosOrderPreparationChange(PosCashRoundingSessionCommon):
    def test_preparation_payload_validation_on_create_and_write(self):
        order = self._create_bare_order()
        invalid_payloads = (
            "{",
            "[]",
            "null",
            "1",
            '{"metadata": []}',
            '{"metadata": {"serverDate": "not-a-date"}}',
            '{"metadata": {"serverDate": 42}}',
            '{"metadata": {"serverDate": []}}',
            '{"metadata": {"serverDate": {}}}',
            '{"metadata": {"serverDate": 0}}',
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                _logger.debug("Rejecting malformed preparation payload %s", payload)
                with self.assertRaises(ValidationError):
                    self._create_bare_order(last_order_preparation_change=payload)
                with self.assertRaises(ValidationError):
                    order.write({"last_order_preparation_change": payload})
                self.assertFalse(order.last_order_preparation_change)

    def test_preparation_validation_preserves_optional_and_extension_fields(self):
        for payload in (
            False,
            "",
            "{}",
            '{"metadata": null}',
            '{"metadata": {"serverDate": false, "extension": 1}}',
            '{"metadata": {"serverDate": "2026-09-13 12:00:00"}, "extension": [1]}',
        ):
            with self.subTest(payload=payload):
                order = self._create_bare_order(last_order_preparation_change=payload)
                self.assertEqual(
                    order.last_order_preparation_change or False, payload or False
                )

    def test_sync_rejects_invalid_preparation_before_merging(self):
        for stored in (False, '{"metadata": {"serverDate": "2026-09-13 12:00:00"}}'):
            for state in ("draft", "paid"):
                with self.subTest(stored=stored, state=state):
                    order = self._create_bare_order(
                        last_order_preparation_change=stored, state=state
                    )
                    values = self._sync_values(order, [])
                    values["last_order_preparation_change"] = '{"metadata": []}'
                    with self.assertRaises(ValidationError):
                        self.env["pos.order"].sync_from_ui([values])
                    self.assertEqual(order.last_order_preparation_change, stored)

    def test_empty_preparation_change_keeps_server_payload(self):
        order = self._create_bare_order(
            last_order_preparation_change=json_dumps(
                {"metadata": {"serverDate": "2026-09-13 12:00:00"}}
            )
        )
        for incoming in (False, None, "", "{}"):
            with self.subTest(incoming=incoming):
                values = {"last_order_preparation_change": incoming}
                order._keep_newest_preparation_change(values)
                self.assertEqual(
                    values["last_order_preparation_change"],
                    order.last_order_preparation_change,
                )

    def test_undated_preparation_change_keeps_dated_server_payload(self):
        order = self._create_bare_order(
            last_order_preparation_change=json_dumps(
                {"metadata": {"serverDate": "2026-09-13 12:00:00"}}
            )
        )
        values = {"last_order_preparation_change": '{"metadata": {"changes": 1}}'}

        order._keep_newest_preparation_change(values)

        self.assertEqual(
            values["last_order_preparation_change"], order.last_order_preparation_change
        )

    def test_dated_preparation_change_replaces_undated_server_payload(self):
        order = self._create_bare_order(
            last_order_preparation_change='{"metadata": {"changes": 1}}'
        )
        values = {
            "last_order_preparation_change": json_dumps(
                {"metadata": {"serverDate": "2026-09-13 12:00:00"}, "lines": {"new": 1}}
            )
        }

        order._keep_newest_preparation_change(values)

        self.assertEqual(
            json_loads(values["last_order_preparation_change"])["lines"], {"new": 1}
        )

    def test_preparation_conflicts_through_finalized_order_sync(self):
        server = json_dumps(
            {"metadata": {"serverDate": "2026-09-13 12:00:00"}, "lines": {"server": 1}}
        )
        for client_date, expected_key in (
            ("2026-09-13 11:59:59", "server"),
            ("2026-09-13 12:00:00", "client"),
            ("2026-09-13 12:00:01", "client"),
        ):
            with self.subTest(client_date=client_date):
                order = self._create_bare_order(
                    state="paid", last_order_preparation_change=server
                )
                values = self._sync_values(order, [])
                values["last_order_preparation_change"] = json_dumps(
                    {
                        "metadata": {"serverDate": client_date},
                        "lines": {"client": 1},
                    }
                )
                expected = deepcopy(values)

                with freeze_time("2026-09-13 12:01:00"):
                    self.env["pos.order"].sync_from_ui([values])

                self.assertEqual(order.state, "paid")
                self.assertEqual(
                    json_loads(order.last_order_preparation_change)["lines"],
                    {expected_key: 1},
                )
                self.assertEqual(values, expected)


@tagged("post_install", "-at_install")
class TestPosOrderPreparationChangeMerge(PosOpenSessionCommon):
    def test_keeping_the_newest_change_needs_a_single_order(self):
        first = self._create_bare_order()
        second = self._create_bare_order()
        with self.assertRaises(ValueError):
            (first | second)._keep_newest_preparation_change({})

    def test_an_older_dated_change_keeps_the_newer_server_payload(self):
        order = self._create_bare_order()
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
