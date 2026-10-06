import warnings
from unittest.mock import patch

from odoo.tests import common, new_test_user


class TestExpandedGroupDisplayNameAccess(common.TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(
            cls.env, login="orm_expand_reader", groups="base.group_system"
        )
        Order = cls.env["test_read_group.order"]
        cls.hidden = Order.create({"name": "Hidden order"})
        cls.visible = Order.create({"name": "Visible order"})
        cls.env["test_read_group.order.line"].create(
            {"order_expand_id": cls.visible.id, "value": 1}
        )

    def _read_names(self, read):
        Order = self.registry["test_read_group.order"]
        original = Order._filtered_display_name_access
        hidden = self.hidden

        def named_unless_hidden(records):
            readable = original(records)
            return readable if records.env.su else readable - hidden

        Line = (
            self.env["test_read_group.order.line"]
            .with_user(self.user)
            .with_context(read_group_expand=True)
        )
        with patch.object(Order, "_filtered_display_name_access", named_unless_hidden):
            groups = read(Line)
        return {
            group["order_expand_id"][0]: group["order_expand_id"][1] for group in groups
        }

    def test_expanded_groups_are_named_under_the_readers_access(self):
        def read(Line):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                return Line.read_group([], ["value:sum"], ["order_expand_id"])

        names = self._read_names(read)
        self.assertEqual(names[self.visible.id], "Visible order")
        self.assertEqual(names[self.hidden.id], "")

    def test_formatted_expanded_groups_are_named_under_the_readers_access(self):
        names = self._read_names(
            lambda Line: Line.formatted_read_group([], ["order_expand_id"], ["__count"])
        )
        self.assertEqual(names[self.visible.id], "Visible order")
        self.assertEqual(names[self.hidden.id], "")
