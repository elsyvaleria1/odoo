import logging
from unittest.mock import patch

from lxml import objectify

from odoo.fields import Command, Domain
from odoo.tools.misc import hmac as hmac_tool

from odoo.addons.base.tests.common import BaseCommon

_logger = logging.getLogger(__name__)


class PaymentCommon(BaseCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.currency_euro = cls._enable_currency("EUR")
        cls.currency_usd = cls._enable_currency("USD")

        cls.country_belgium = cls.quick_ref("base.be")
        cls.country_france = cls.quick_ref("base.fr")
        cls.europe = cls.quick_ref("base.europe")

        cls.admin_user = cls.quick_ref("base.user_admin")
        cls.internal_user = cls._create_new_internal_user()
        cls.portal_user = cls._create_new_portal_user()
        cls.public_user = cls.quick_ref("base.public_user")

        cls.admin_partner = cls.admin_user.partner_id
        cls.internal_partner = cls.internal_user.partner_id
        cls.portal_partner = cls.portal_user.partner_id
        cls.default_partner = cls.env["res.partner"].create(
            {
                "name": "Norbert Buyer",
                "lang": "en_US",
                "email": "norbert.buyer@example.com",
                "street": "Huge Street",
                "street2": "2/543",
                "phone_ids": [
                    Command.create({"number": "0032 12 34 56 78", "type": "landline"})
                ],
                "city": "Sin City",
                "zip": "1000",
                "country_id": cls.country_belgium.id,
            }
        )

        arch = """
        <form action="dummy" method="post">
            <input type="hidden" name="view_id" t-att-value="viewid"/>
            <input type="hidden" name="user_id" t-att-value="user_id.id"/>
        </form>
        """
        redirect_form = cls.env["ir.ui.view"].create(
            {
                "name": "Dummy Redirect Form",
                "type": "qweb",
                "arch": arch,
            }
        )

        cls.pm_unknown = cls.quick_ref("payment.payment_method_unknown")
        cls.dummy_provider = cls.env["payment.provider"].create(
            {
                "name": "Dummy Provider",
                "code": "none",
                "state": "test",
                "is_published": True,
                "payment_method_ids": [Command.set([cls.pm_unknown.id])],
                "allow_tokenization": True,
                "redirect_form_view_id": redirect_form.id,
                "available_currency_ids": [
                    Command.set(
                        (
                            cls.currency_euro
                            + cls.currency_usd
                            + cls.env.company.currency_id
                        ).ids
                    )
                ],
            }
        )
        cls.pm_unknown.write(
            {
                "active": True,
                "support_tokenization": True,
            }
        )

        cls.provider = cls.dummy_provider
        cls.payment_methods = cls.provider.payment_method_ids
        cls.payment_method = cls.payment_methods[:1]
        cls.payment_method_id = cls.payment_method.id
        cls.payment_method_code = cls.payment_method.code
        cls.amount = 1111.11
        cls.company = cls.env.company
        cls.company_id = cls.company.id
        cls.currency = cls.currency_euro
        cls.partner = cls.default_partner
        cls.reference = "Test Transaction"

        account_payment_module = cls.env["ir.module.module"]._get(
            "account_payment_provider"
        )
        cls.account_payment_installed = account_payment_module.state in (
            "installed",
            "to upgrade",
        )
        cls.enable_post_process_patcher = True

    def setUp(self):
        super().setUp()
        if self.account_payment_installed and self.enable_post_process_patcher:
            self.post_process_patcher = patch(
                "odoo.addons.account_payment_provider.models.payment_transaction.PaymentTransaction._post_process",
            )
            self.startPatcher(self.post_process_patcher)

    @classmethod
    def _prepare_provider(cls, code, company=None, update_values=None, **kwargs):
        assert code != "none", "Code 'none' should not be passed to _prepare_provider"

        company = company or cls.env.company
        update_values = update_values or {}
        provider_domain = cls._get_domain_provider(code, **kwargs)

        provider = (
            cls.env["payment.provider"]
            .sudo()
            .search(
                Domain.AND([provider_domain, [("company_id", "=", company.id)]]),
                limit=1,
            )
        )
        if not provider:
            _logger.error(
                "No payment.provider found for code %s in company %s",
                code,
                company.name,
            )
            return cls.env["payment.provider"]

        update_values["state"] = "test"
        provider.write(update_values)
        return provider

    @classmethod
    def _get_domain_provider(cls, code, **kwargs):
        return [("code", "=", code)]

    @classmethod
    def _prepare_user(cls, user, group_xmlid):
        user.group_ids = [Command.link(cls.env.ref(group_xmlid).id)]
        user.flush_recordset()
        user.invalidate_recordset()
        return user

    def _create_transaction(self, flow, sudo=True, **values):
        default_values = {
            "payment_method_id": self.payment_method_id,
            "amount": self.amount,
            "currency_id": self.currency.id,
            "provider_id": self.provider.id,
            "reference": self.reference,
            "operation": f"online_{flow}",
            "partner_id": self.partner.id,
        }
        return (
            self.env["payment.transaction"]
            .sudo(sudo)
            .create(dict(default_values, **values))
        )

    def _create_token(self, sudo=True, **values):
        default_values = {
            "provider_id": self.provider.id,
            "payment_method_id": self.payment_method_id,
            "payment_details": "1234",
            "partner_id": self.partner.id,
            "provider_ref": "provider Ref (TEST)",
            "active": True,
        }
        return (
            self.env["payment.token"].sudo(sudo).create(dict(default_values, **values))
        )

    def _get_tx(self, reference):
        return (
            self.env["payment.transaction"]
            .sudo()
            .search(
                [
                    ("reference", "=", reference),
                ]
            )
        )

    def _generate_test_access_token(self, *values):
        token_str = "|".join(str(val) for val in values)
        return hmac_tool(self.env(su=True), "generate_access_token", token_str)

    def _extract_values_from_html_form(self, html_form):
        html_tree = objectify.fromstring(html_form)
        if hasattr(html_tree, "input"):
            inputs = {
                input_.get("name"): input_.get("value") for input_ in html_tree.input
            }
        else:
            inputs = {}
        return {
            "action": html_tree.get("action"),
            "method": html_tree.get("method"),
            "inputs": inputs,
        }

    def _assert_does_not_raise(self, exception_class, func, *args, **kwargs):
        try:
            func(*args, **kwargs)
        except exception_class:
            self.fail(
                f"{func.__name__} should not raise error of class {exception_class.__name__}"
            )
        except Exception:
            pass

    def _skip_if_account_payment_is_not_installed(self):
        if not self.account_payment_installed:
            self.skipTest("account_payment_provider module is not installed")
