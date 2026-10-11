import base64
import csv
import logging
import secrets
import string
import uuid
from typing import Any
from urllib.parse import urlparse

from werkzeug.wrappers import Response

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.tools import file_open
from odoo.tools.safe_eval import time

from odoo.addons.hr_expense_stripe.controllers.main import StripeIssuingController
from odoo.addons.hr_expense_stripe.utils import (
    COUNTRY_MAPPING,
    STRIPE_VALID_JOURNAL_CURRENCIES,
    StripeIssuingDatabaseError,
    send_request_stripe_proxy,
)
from odoo.addons.integration.tools.admission import Resolution

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    stripe_id = fields.Char(
        string="Stripe Account ID",
        copy=False,
        groups="base.group_system",
    )
    stripe_account_issuing_status = fields.Selection(
        selection=[
            ("restricted", "Restricted"),
            ("verified", "Verified"),
        ],
        string="Status",
        default="restricted",
    )

    stripe_journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Stripe Issuing Journal",
        copy=False,
        domain=[
            ("type", "=", "bank"),
            ("bank_statements_source", "=", "stripe_issuing"),
        ],
        check_company=True,
    )
    stripe_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_stripe_currency",
        store=True,
        copy=False,
        readonly=True,
    )
    stripe_issuing_activated = fields.Boolean(readonly=True)
    stripe_account_issuing_tos_accepted = fields.Boolean(groups="base.group_system")
    stripe_account_issuing_tos_acceptance_date = fields.Date(groups="base.group_system")
    stripe_issuing_iap_webhook_uuid = fields.Char(groups="base.group_system")

    stripe_issuing_db_private_key_id = fields.Many2one(
        comodel_name="certificate.key",
        copy=False,
        readonly=True,
        groups="base.group_system",
    )
    stripe_issuing_iap_public_key_id = fields.Many2one(
        comodel_name="certificate.key",
        copy=False,
        readonly=True,
        groups="base.group_system",
    )

    _constraint_journal_stripe_activated = models.Constraint(
        definition="CHECK(NOT stripe_issuing_activated OR (stripe_journal_id IS NOT NULL AND stripe_issuing_activated))",
        message="You cannot remove the journal used by Stripe Issuing when it is activated",
    )

    @api.depends("country_id", "tax_config_id.account_fiscal_country_id")
    def _compute_stripe_currency(self) -> None:
        for company in self:
            company_country = company.tax_config_id.account_fiscal_country_id
            if "EU" in (company_country.country_group_codes or []):
                company_currency_code = STRIPE_VALID_JOURNAL_CURRENCIES["EU"]
            elif company_country.code == "gb":
                company_currency_code = STRIPE_VALID_JOURNAL_CURRENCIES["UK"]
            else:
                company_currency_code = (
                    STRIPE_VALID_JOURNAL_CURRENCIES.get(company_country.code) or "USD"
                )
            currency = self.env["res.currency"].search(
                [("name", "=ilike", company_currency_code)], limit=1
            )
            company.stripe_currency_id = currency and currency.id

    def _stripe_issuing_setup_mcc(self) -> None:
        mcc_data = self.env["ir.model.data"]._read_group(
            [("model", "=", "product.mcc.stripe.tag")],
            groupby=["name"],
            aggregates=[
                "res_id:array_agg"
            ],
        )
        ref_to_mcc = {}
        mcc_prefetch_ids = []
        for ref, (res_id,) in mcc_data:
            mcc_prefetch_ids.append(res_id)
            ref_to_mcc[ref] = (
                self.env["product.mcc.stripe.tag"]
                .browse(res_id)
                .with_prefetch(mcc_prefetch_ids)
            )

        products_referenced = set()
        mcc_ref_to_product_ref = {}
        with file_open(
            "hr_expense_stripe/data/template/product.mcc.stripe.tag.csv", "rt"
        ) as csv_file:
            for row in csv.DictReader(csv_file):
                product_ref_name = row["product_id"].split(".", 1)[-1]
                mcc_ref_to_product_ref[row["id"]] = product_ref_name
                products_referenced.add(product_ref_name)

        product_data = self.env["ir.model.data"]._read_group(
            [
                ("model", "=", "product.product"),
                ("name", "in", tuple(products_referenced)),
            ],
            groupby=["name"],
            aggregates=[
                "res_id:array_agg"
            ],
        )
        ref_to_product = {}
        product_prefetch_ids = []
        for ref, (res_id,) in product_data:
            product_prefetch_ids.append(res_id)
            ref_to_product[ref] = (
                self.env["product.product"]
                .browse(res_id)
                .with_prefetch(product_prefetch_ids)
            )

        available_to_all_companies = self.browse()
        for company in self:
            for mcc_ref, product_ref in mcc_ref_to_product_ref.items():
                mcc = ref_to_mcc.get(mcc_ref).with_company(company)
                product = ref_to_product.get(product_ref)
                if (
                    mcc
                    and not mcc.product_id
                    and product
                    and product.company_id in {available_to_all_companies, company}
                ):
                    mcc.product_id = product.id

    def _prepare_account_creation_payload(self) -> dict[str, Any]:
        self.check_singleton()
        country_code = COUNTRY_MAPPING.get(self.country_id.code, self.country_id.code)
        return {
            "country": country_code,
        }

    def _prepare_account_links_payload(self) -> dict[str, str]:
        self.check_singleton()
        return_url = f"{self._get_stripe_issuing_base_url()}/odoo/settings#hr_expense"
        return {
            "account": self.stripe_id,
            "refresh_url": return_url,
            "return_url": return_url,
        }

    def _get_stripe_webhook_url(self, uuid=None):
        self.check_singleton()
        return "/".join(
            (
                self._get_stripe_issuing_base_url(),
                StripeIssuingController._webhook_url,
                uuid or self.stripe_issuing_iap_webhook_uuid,
            )
        )

    def _get_stripe_issuing_base_url(self) -> str:
        base_url = self.get_base_url()
        _scheme, netloc, *_rest = urlparse(base_url)
        return f"https://{netloc}"

    @api.model
    def _receiver_for_stripe_issuing(self, company_uuid, **path_args):
        company = self.sudo().search(
            [("stripe_issuing_iap_webhook_uuid", "=", company_uuid)], limit=1
        )
        if not company:
            return company

        def is_request_authorized(headers, body) -> bool:
            return company._is_stripe_issuing_signature_valid(
                headers.get("Iap-Signature"), body.decode()
            )

        try:
            payload = request.get_json_data() if request else None
        except ValueError:
            payload = None
        return Resolution(
            company,
            gate=(
                company,
                "%s Stripe Issuing webhook" % company.name,
                "stripe_issuing",
            ),
            verify=is_request_authorized,
            event_id=(payload.get("id") if isinstance(payload, dict) else None) or None,
        )

    @api.model
    def _refuse_stripe_issuing(self, refused):
        if refused.error_code == "duplicate_event":
            return Response("", status=200)
        status = {
            404: StripeIssuingDatabaseError.DB_WRONG_WEBHOOK,
            401: StripeIssuingDatabaseError.DB_WRONG_SIGNATURE,
        }.get(refused.status, refused.status)
        message = {
            404: "Invalid webhook accessed",
            401: "Invalid or outdated signature found in the request",
        }.get(refused.status, refused.reason)
        return Response(
            json_dumps({"message": message}),
            status=status,
            content_type="application/json",
        )

    def _is_stripe_issuing_signature_valid(self, signature_header, payload_str) -> bool:
        self.check_singleton()
        if not signature_header:
            return False

        signature_data_dict = {}
        for key_value_str in signature_header.split(","):
            key, _sep, value = key_value_str.partition("=")
            if key in signature_data_dict:
                return False
            signature_data_dict[key] = value

        if "v1" not in signature_data_dict or "t" not in signature_data_dict:
            return False

        signature = base64.b64decode(
            signature_data_dict["v1"] + "=="
        )
        timestamp = signature_data_dict["t"]
        try:
            time_since_signed = time.time() - int(timestamp)
        except ValueError:
            return False
        signature_validity = 60 * 5
        if time_since_signed > signature_validity:
            return False
        signed_message = f"{timestamp}.{payload_str}".encode()
        public_key = self.sudo().stripe_issuing_iap_public_key_id
        return public_key._execute_signature_verification(signed_message, signature)

    @api.model
    def _get_stripe_mode(self):
        key = "hr_expense_stripe.stripe_mode"
        mode = self.env.registry.settings.get(self.env, key, "live")
        if mode not in {"live", "test"}:
            raise ValidationError(
                self.env._(
                    "System parameter '%(name)s' value is incorrect, expecting 'live', 'test' or no value",
                    name=key,
                )
            )
        return mode

    def _create_stripe_issuing_journal(self) -> None:
        for company in self:
            ChartTemplate = self.env["account.chart.template"].with_company(company)
            journal = ChartTemplate.ref(
                "stripe_issuing_journal", raise_if_not_found=False
            )
            if not company.stripe_currency_id:
                continue
            if not journal:
                self.env["account.journal"].with_company(company)._load_records(
                    [
                        {
                            "xml_id": f"account.{company.id}_{xml_id}",
                            "values": values,
                            "noupdate": True,
                        }
                        for xml_id, values in ChartTemplate._get_stripe_issuing_account_journal(
                            None
                        ).items()
                    ]
                )
                journal = ChartTemplate.ref("stripe_issuing_journal")
            if not journal.active:
                journal.active = True
            if not company.stripe_journal_id:
                company.stripe_journal_id = journal

    def _cron_refresh_stripe_account(self) -> None:
        for company in self.env["res.company"].search([("stripe_id", "!=", False)]):
            company.action_refresh_stripe_account()

    def action_create_stripe_account(self):
        self.check_singleton()
        if self.stripe_id:
            return self.action_configure_stripe_account()

        self._create_stripe_account()
        return self.action_configure_stripe_account()

    def _create_stripe_account(self) -> None:
        self.check_singleton()
        if self.stripe_issuing_iap_webhook_uuid:
            raise UserError(
                self.env._("A Webhook URL already exists for this company.")
            )

        if not self.stripe_journal_id:
            self._create_stripe_issuing_journal()
            self.stripe_journal_id = self.env.ref(
                f"account.{self.id}_stripe_issuing_journal"
            )

        if not self.stripe_journal_id.currency_id:
            self.stripe_journal_id.currency_id = self.stripe_currency_id

        printable_characters_no_spaces = (
            string.digits + string.ascii_letters + string.punctuation
        )
        random_password = "".join(
            secrets.choice(printable_characters_no_spaces) for _i in range(36)
        )
        db_private_key = self.env["certificate.key"]._generate_ed25519_private_key(
            company=self,
            name=self.env._("Private key used for Stripe Issuing"),
            password=random_password,
        )
        stripe_issuing_iap_webhook_uuid = str(uuid.uuid4())
        payload = {
            **self._prepare_account_creation_payload(),
            "db_webhook_url": self._get_stripe_webhook_url(
                stripe_issuing_iap_webhook_uuid
            ),
            "db_public_key": db_private_key._get_public_key_bytes().decode(),
            "db_uuid": self.env.registry.settings.get(self.env, "database.uuid", False),
            "accepted_tos": self.stripe_account_issuing_tos_accepted,
        }
        payload = {key: value for key, value in payload.items() if value is not False}
        response = send_request_stripe_proxy(
            self.sudo(), "accounts", payload=payload, method="POST"
        )
        iap_public_key = self.env["certificate.key"].create(
            [
                {
                    "name": self.env._("IAP Public key used for Stripe Issuing"),
                    "content": response["iap_public_key"],
                    "company_id": self.id,
                }
            ]
        )
        self.write(
            {
                "stripe_id": response["id"],
                "stripe_issuing_iap_webhook_uuid": stripe_issuing_iap_webhook_uuid,
                "stripe_account_issuing_tos_accepted": True,
                "stripe_account_issuing_tos_acceptance_date": fields.Date.today(),
                "stripe_issuing_db_private_key_id": db_private_key.id,
                "stripe_issuing_iap_public_key_id": iap_public_key.id,
            }
        )
        self.env["ir.config_parameter"].sudo().set_param(
            f"hr_expense_stripe.{self.id}_stripe_issuing_pk", response["stripe_pk"]
        )

        self.stripe_issuing_activated = True
        cron = self.env.ref(
            "hr_expense_stripe.hr_expense_stripe_issuing_status_cron",
            raise_if_not_found=False,
        )
        if cron and not cron.active:
            cron.active = True

        if not self.env.context.get("skip_stripe_account_creation_commit"):
            self.env["ir.cron"]._commit_progress()

    def action_refresh_stripe_account(self):
        for company in self.filtered("stripe_id"):
            response = send_request_stripe_proxy(
                company.sudo(),
                "accounts/{account}",
                route_params={"account": company.sudo().stripe_id},
                method="GET",
            )

            if response["capabilities"]["card_issuing"] == "active":
                company.stripe_account_issuing_status = "verified"
            else:
                company.stripe_account_issuing_status = "restricted"

            current_pk = company.env.registry.settings.get(
                company.env, f"hr_expense_stripe.{company.id}_stripe_issuing_pk", False
            )
            if current_pk != response["stripe_pk"]:
                company.env["ir.config_parameter"].sudo().set_param(
                    f"hr_expense_stripe.{company.id}_stripe_issuing_pk",
                    response["stripe_pk"],
                )

    def action_configure_stripe_account(self):
        self.check_singleton()

        if not self.sudo().stripe_id:
            raise ValidationError(
                self.env._(
                    "You need to be connected to stripe in order to configure your account."
                )
            )

        payload = self._prepare_account_links_payload()
        response = send_request_stripe_proxy(
            self.sudo(), "account_links", payload=payload, method="POST"
        )
        return {
            "type": "ir.actions.act_url",
            "url": response["url"],
            "target": "self",
        }
