from datetime import date
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from odoo.addons.account.models.account_journal import AccountJournal

_debug = DebugLog(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    iso20022_uetr = fields.Char(
        string="UETR",
        help="Unique end-to-end transaction reference",
    )

    def _acquire_iso20022_payments_data(
        self, journal_id: AccountJournal, payment_date: date | None = None
    ) -> list[dict[str, Any]]:
        self.check_singleton()
        payment_date = payment_date or fields.Date.today()
        payments = []
        if journal_id.sepa_pain_version == "pain.001.001.09":
            if not self.iso20022_uetr:
                iso20022_uetr = self.iso20022_uetr = str(uuid4())
            else:
                iso20022_uetr = self.iso20022_uetr
        else:
            iso20022_uetr = False

        allocations = self.compute_salary_allocations()
        _debug.logic(
            "sepa_payslip_allocations",
            payslip=self,
            employee=self.employee_id,
            bank_accounts=len(self.employee_id.salary_bank_account_ids),
            allocated=len(allocations),
            # the reference is generated ONCE and stored, so a regenerated
            # file reuses it -- which is the ISO20022 contract and also means
            # a corrected file is indistinguishable from a duplicate
            uetr_reused=bool(self.iso20022_uetr) and bool(iso20022_uetr),
            pain_version=journal_id.sepa_pain_version,
        )
        for ba in self.employee_id.salary_bank_account_ids:
            amount = allocations[str(ba.id)]
            if not amount:
                _debug.logic(
                    "sepa_allocation_skipped",
                    reason="allocation_is_zero",
                    payslip=self,
                    bank_account=ba,
                )
                continue
            payment = {
                "id": self.id,
                "name": str(self.id),
                "payment_date": payment_date,
                "amount": amount,
                "journal_id": journal_id.id,
                "currency_id": journal_id.currency_id.id,
                "payment_type": "outbound",
                "memo": str(self.id),
                "partner_id": self.employee_id.partner_id.id,
                "bank_account_id": ba.id,
                "iso20022_charge_bearer": journal_id.iso20022_charge_bearer,
                # The "High" priority level is a payment attribute that we should specify for salary payments :
                # https://www.febelfin.be/sites/default/files/2019-04/standard-credit_transfer-xml-v32-en_0.pdf
                # section 2.6
                "iso20022_priority": "HIGH"
                if journal_id.company_id.tax_config_id.account_fiscal_country_id.code
                == "BE"
                else "NORM",
            }
            if iso20022_uetr:
                payment["iso20022_uetr"] = iso20022_uetr
            payments.append(payment)
        _debug.pipeline(
            "sepa_payslip_payments",
            payslip=self,
            payments=len(payments),
            payment_date=payment_date,
            # HIGH only for a Belgian company, per Febelfin; every other
            # country's salary payments go out at NORM
            priority="HIGH"
            if journal_id.company_id.tax_config_id.account_fiscal_country_id.code
            == "BE"
            else "NORM",
        )
        return payments

    def action_payslip_payment_report(self, export_format="sepa"):
        action = super().action_payslip_payment_report()
        if self.company_id.currency_id.name != "EUR":
            return action
        action.update(
            {
                "context": {
                    **action["context"],
                    "default_export_format": export_format,
                },
            }
        )
        return action
