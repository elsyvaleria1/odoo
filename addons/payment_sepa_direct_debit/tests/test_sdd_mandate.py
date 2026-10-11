from odoo.tests import tagged

from odoo.addons.payment_sepa_direct_debit.tests.common import SepaDirectDebitCommon


@tagged("-at_install", "post_install")
class TestSepaDirectDebitMandate(SepaDirectDebitCommon):
    def test_source_transaction_is_the_first(self):
        source_tx = self._create_transaction(
            flow="direct", state="done", mandate_id=self.mandate.id
        )
        token = self.env["payment.token"].search(
            [("sdd_mandate_id", "=", self.mandate.id)]
        )

        self._create_transaction(
            token_id=token.id,
            flow="token",
            state="done",
            mandate_id=self.mandate.id,
            reference=f"Other-{source_tx.reference}",
        )

        result_tx = self.mandate._get_source_transaction()

        self.assertEqual(
            result_tx, source_tx, "Expected the source transaction of this mandate"
        )

    def test_user_with_bank_account_validation_role_can_validate_mandates(self):
        self.mandate.with_user(self.user).action_validate_mandate()
