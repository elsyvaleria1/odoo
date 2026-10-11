from odoo.exceptions import ValidationError
from odoo.tests import tagged

from odoo.addons.payment_mercado_pago.tests.common import MercadoPagoCommon


@tagged("post_install", "-at_install")
class TestPaymentProvider(MercadoPagoCommon):
    def test_allow_enabling_if_credentials_are_set(self):
        self._assert_does_not_raise(
            ValidationError, self.provider.write({"state": "enabled"})
        )

    def test_prevent_enabling_if_credentials_are_not_set(self):
        self.provider.action_reset_credentials()
        with self.assertRaises(ValidationError):
            self.provider.state = "enabled"

    def test_incompatible_with_unsupported_currencies(self):
        compatible_providers = self.env["payment.provider"]._get_compatible_providers(
            self.company_id,
            self.partner.id,
            self.amount,
            currency_id=self.env.ref("base.AFN").id,
        )
        self.assertNotIn(self.provider, compatible_providers)
