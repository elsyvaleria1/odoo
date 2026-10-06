from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import TelegramBotTestCase


@tagged("post_install", "-at_install")
class TestPartnerMergeKeepsTelegramIdentity(TelegramBotTestCase):
    def test_a_binding_follows_the_contact_it_was_merged_into(self):
        destination = self._create_partner({"name": "Merge Destination"})
        source = self._create_partner({"name": "Merge Source"})
        account = self._bound_account("660001", source)

        wizard = self.env["wizard.res.partner.merge"].create({})
        wizard._merge((destination | source).ids, destination, extra_checks=False)
        self.env.invalidate_all()

        self.assertFalse(source.exists())
        self.assertEqual(account.partner_id, destination)
        self.assertEqual(account.binding_id.partner_id, destination)

    def test_a_stand_in_the_merge_refuses_keeps_its_history_and_the_binding_stands(
        self,
    ):
        account = self.env["telegram.account"]._from_telegram(
            {"id": 660002, "first_name": "Visitante"}
        )
        stand_in = account._contact()
        proven = self._create_partner({"name": "Proven Contact"})
        merge = type(self.env["wizard.res.partner.merge"])
        with patch.object(merge, "_merge", side_effect=UserError("hashed entry")):
            binding = account._bind(proven, method="invitation")

        self.assertEqual(account.binding_id, binding)
        self.assertEqual(binding.partner_id, proven)
        self.assertTrue(stand_in.exists())
