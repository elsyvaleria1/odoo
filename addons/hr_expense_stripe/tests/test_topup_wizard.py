from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools.translate import code_translations


@tagged("post_install", "-at_install")
class TestTopupWizardQrCode(TransactionCase):
    def test_qr_caption_translation_is_escaped(self):
        self.env["res.lang"]._activate_lang("fr_FR")
        key = ("hr_expense_stripe", "fr_FR")
        code_translations.python_translations[key] = {
            **code_translations.get_python_translations(*key),
            "Scan me with your banking app.": "Scannez <b>ici</b> & payez",
        }
        self.addCleanup(code_translations.python_translations.pop, key)
        company = self.env.company
        company.country_id = self.env.ref("base.be")
        bank = self.env["res.partner.bank.account"].create(
            {
                "acc_number": "BE71096123456769",
                "partner_id": company.partner_id.id,
                "allow_out_payment": True,
            }
        )
        self.assertTrue(bank.allow_out_payment)
        wizard = (
            self.env["wizard.account.journal.topup"]
            .with_context(lang="fr_FR")
            .create(
                {
                    "company_id": company.id,
                    "currency_id": company.currency_id.id,
                    "bank_account_id": bank.id,
                    "amount": 100.0,
                }
            )
        )
        with patch.object(
            type(bank),
            "prepare_qr_code_base64",
            return_value="data:image/png;base64,QUJD",
        ):
            qr_code = str(wizard.qr_code)

        self.assertIn('src="data:image/png;base64,QUJD"', qr_code)
        self.assertIn("Scannez &lt;b&gt;ici&lt;/b&gt; &amp; payez", qr_code)
        self.assertNotIn("<b>ici</b>", qr_code)
