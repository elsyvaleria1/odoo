from datetime import date

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.common import PaymentCommon


@tagged("-at_install", "post_install")
class TestPaymentToken(PaymentCommon):
    @mute_logger("odoo.addons.base.models.ir_access")
    def test_users_have_no_access_to_other_users_tokens(self):
        users = [self.public_user, self.portal_user, self.internal_user]
        token = self._create_token(partner_id=self.admin_partner.id)
        for user in users:
            with self.assertRaises(AccessError):
                token.with_user(user).read()

    def test_cannot_assign_token_to_public_partner(self):
        token = self._create_token()
        with self.assertRaises(ValidationError):
            token.partner_id = self.public_user.partner_id

    def test_unarchiving_token_requires_active_provider(self):
        token = self._create_token(active=False)
        token.provider_id.state = "disabled"
        with self.assertRaises(UserError):
            token.active = True

    def test_unarchiving_token_requires_active_payment_method(self):
        token = self._create_token(active=False)
        token.payment_method_id.active = False
        with self.assertRaises(UserError):
            token.active = True

    def test_display_name_is_padded(self):
        token = self._create_token()
        self.assertEqual(token._prepare_display_name(), "•••• 1234")

    @freeze_time("2024-01-31 10:00:00")
    def test_display_name_for_empty_payment_details(self):
        token = self._create_token(payment_details="")
        self.env.cr.execute(
            "UPDATE payment_token SET create_date = %s WHERE id = %s",
            params=(date.today(), token.id),
        )
        token.invalidate_recordset(fnames=["create_date"])
        self.assertEqual(
            token._prepare_display_name(),
            f"Payment details saved on {date.today().strftime('%Y/%m/%d')}",
        )

    def test_display_name_is_shortened_to_max_length(self):
        token = self._create_token()
        self.assertEqual(token._prepare_display_name(max_length=6), "• 1234")

    def test_display_name_is_not_padded(self):
        token = self._create_token()
        self.assertEqual(token._prepare_display_name(should_pad=False), "1234")
