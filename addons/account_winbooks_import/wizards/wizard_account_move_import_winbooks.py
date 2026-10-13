import base64
import collections
import io
import itertools
import logging
import pathlib
import re
import zipfile
from datetime import datetime, timedelta
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from dbfread import DBF

from odoo import Command, fields, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.tools import frozendict

if TYPE_CHECKING:
    from odoo.addons.account.models.account_account_tag import AccountAccountTag

_logger = logging.getLogger(__name__)


PURCHASE_CODE = "0"
SALE_CODE = "2"
CREDIT_NOTE_PURCHASE_CODE = "1"
CREDIT_NOTE_SALE_CODE = "3"


class WizardAccountMoveImportWinbooks(models.TransientModel):
    _name = "wizard.account.move.import.winbooks"
    _description = "Account Winbooks import wizard"

    zip_file = fields.Binary(
        string="File",
        required=True,
    )
    only_open = fields.Boolean(
        string="Import only open years",
        default=True,
        help="Years closed in Winbooks are likely to have incomplete data. The counter part of incomplete entries will be set in a suspense account",
    )
    suspense_code = fields.Char(
        string="Suspense Account Code",
        help="This is the code of the account in which you want to put the counterpart of unbalanced moves. This might be an account from your Winbooks data, or an account that you created in Odoo before the import.",
    )

    def _import_partner_info(self, dbf_records):
        _logger.info("Import Partner Infos")
        category_data = {}
        ResPartnerTag = self.env["res.partner.tag"]
        for rec in dbf_records:
            if rec.get("TTYPE").startswith("CAT"):
                category = ResPartnerTag.search(
                    [("name", "=", rec.get("TDESC"))], limit=1
                )
                if not category:
                    category = ResPartnerTag.create({"name": rec.get("TDESC")})
                category_data[rec.get("TID")] = category.id
        return category_data

    def _import_partner(self, dbf_records, category_data, account_data) -> tuple:
        _logger.info("Import Partners")
        partner_data = {}
        ResBank = self.env["res.bank"]
        ResCountry = self.env["res.country"]
        ResPartner = self.env["res.partner"]
        ResPartnerBankAccount = self.env["res.partner.bank.account"]
        partner_data_dict = {}
        for rec in dbf_records:
            if not rec.get("NUMBER"):
                continue
            partner = ResPartner.search([("ref", "=", rec.get("NUMBER"))], limit=1)
            if partner:
                partner_data[rec.get("NUMBER")] = partner.id
            if not partner:
                vatcode = (
                    rec.get("VATNUMBER")
                    and rec.get("COUNTRY")
                    and (rec.get("COUNTRY") + rec.get("VATNUMBER").replace(".", ""))
                )
                if (
                    not rec.get("VATNUMBER")
                    or not rec.get("COUNTRY")
                    or not ResPartner._check_vat_number(
                        rec.get("COUNTRY").upper(), vatcode
                    )
                ):
                    vatcode = ""
                data = {
                    "ref": rec.get("NUMBER"),
                    "name": rec.get("NAME1"),
                    "street": rec.get("ADRESS1"),
                    "country_id": ResCountry.search(
                        [("code", "=", rec.get("COUNTRY"))], limit=1
                    ).id,
                    "city": rec.get("CITY"),
                    "street2": rec.get("ADRESS2"),
                    "vat": vatcode,
                    "phone_ids": [
                        Command.create(
                            {"number": rec.get("TELNUMBER"), "type": "landline"}
                        )
                    ]
                    if rec.get("TELNUMBER")
                    else False,
                    "zip": rec.get("ZIPCODE")
                    and "".join([n for n in rec.get("ZIPCODE") if n.isdigit()]),
                    "email": rec.get("EMAIL"),
                    "active": not rec.get("ISLOCKED"),
                    "category_id": [
                        Command.set([category_data.get(rec.get("CATEGORY"))])
                    ]
                    if category_data.get(rec.get("CATEGORY"))
                    else False,
                }
                if partner_data_dict.get(rec.get("NUMBER")):
                    data.update(
                        {
                            key: value
                            for key, value in partner_data_dict[
                                rec.get("NUMBER")
                            ].items()
                            if value
                        }
                    )
                if rec.get("NAME2"):
                    data["child_ids"] = [Command.create({"name": rec["NAME2"]})]
                if rec.get("IBANAUTO"):
                    partner_bank = ResPartnerBankAccount.search(
                        [("acc_number", "=", rec.get("IBANAUTO"))], limit=1
                    )
                    if partner_bank:
                        data["bank_account_ids"] = [Command.link(partner_bank.id)]
                    else:
                        bank = ResBank.search(
                            [("name", "=", rec.get("BICAUTO"))], limit=1
                        )
                        if not bank:
                            bank = ResBank.create({"name": rec.get("BICAUTO")})
                        data.update(
                            {
                                "bank_account_ids": [
                                    Command.create(
                                        {
                                            "acc_number": rec.get("IBANAUTO"),
                                            "bank_id": bank.id,
                                        }
                                    )
                                ],
                            }
                        )
                if rec.get("CENTRAL"):
                    if rec.get("TYPE") == "1":
                        data["property_account_receivable_id"] = account_data[
                            rec.get("CENTRAL")
                        ]
                    else:
                        data["property_account_payable_id"] = account_data[
                            rec.get("CENTRAL")
                        ]

                partner_data_dict[rec.get("NUMBER")] = data
                if len(partner_data_dict) % 100 == 0:
                    _logger.info("Advancement: %s", len(partner_data_dict))

        partner_ids = ResPartner.create(tuple(partner_data_dict.values()))
        for partner in partner_ids:
            partner_data[partner.ref] = partner.id
        return partner_data, partner_ids

    def _import_account(self, dbf_records) -> tuple:

        def manage_centralid(account, centralid, skip_constraints_check=False):
            property_name = None
            account_central[centralid] = account.id
            tax_group_name = None
            if centralid == "S1":
                property_name = "property_account_payable_id"
                model_name = "res.partner"
            if centralid == "C1":
                property_name = "property_account_receivable_id"
                model_name = "res.partner"
            if centralid == "V01":
                tax_group_name = "tax_receivable_account_id"
            if centralid == "V03":
                tax_group_name = "tax_payable_account_id"
            if property_name:
                self.env["ir.default"].set(
                    model_name,
                    property_name,
                    account.id,
                    company_id=self.env.company.id,
                )
            if tax_group_name:
                self.env["account.tax.group"].search(
                    self.env["account.tax.group"]._get_domain_company_compatible(
                        self.env.company
                    )
                ).with_context(skip_constraints_check=skip_constraints_check)[
                    tax_group_name
                ] = account

        _logger.info("Import Accounts")
        account_data = {}
        account_central = {}
        account_tax = {}
        grouped = collections.defaultdict(list)
        AccountAccount = self.env["account.account"]
        ResCurrency = self.env["res.currency"]
        AccountGroup = self.env["account.group"]
        account_types = [
            {"min": 100, "max": 160, "id": "equity"},
            {"min": 160, "max": 200, "id": "liability_non_current"},
            {"min": 200, "max": 280, "id": "asset_non_current"},
            {"min": 280, "max": 290, "id": "asset_fixed"},
            {"min": 290, "max": 420, "id": "asset_current"},
            {"min": 420, "max": 490, "id": "liability_current"},
            {"min": 490, "max": 492, "id": "asset_current"},
            {"min": 492, "max": 500, "id": "liability_current"},
            {"min": 500, "max": 600, "id": "asset_cash"},
            {"min": 600, "max": 700, "id": "expense"},
            {"min": 700, "max": 822, "id": "income"},
            {"min": 822, "max": 860, "id": "expense"},
        ]
        for rec in dbf_records:
            grouped[rec.get("TYPE")].append(rec)
        rec_number_list = []
        account_data_list = []
        journal_centered_list = []
        is_deprecated_list = []
        account_deprecated_ids = self.env["account.account"]
        for key, val in grouped.items():
            if key == "3":
                for rec in val:
                    account = AccountAccount.search(
                        [
                            *AccountAccount._get_domain_company_compatible(
                                self.env.company
                            ),
                            ("code", "=", rec.get("NUMBER")),
                        ],
                        limit=1,
                    )
                    if account:
                        account_data[rec.get("NUMBER")] = account.id
                        rec["CENTRALID"] and manage_centralid(
                            account, rec["CENTRALID"], skip_constraints_check=True
                        )
                    if not account and rec.get("NUMBER") not in rec_number_list:
                        data = {
                            "code": rec.get("NUMBER"),
                            "name": rec.get("NAME11"),
                            "group_id": AccountGroup.search(
                                [("code_prefix_start", "=", rec.get("CATEGORY"))],
                                limit=1,
                            ).id,
                            "currency_id": ResCurrency.search(
                                [("name", "=", rec.get("CURRENCY"))], limit=1
                            ).id,
                        }
                        if rec.get("VATCODE"):
                            account_tax[rec.get("NUMBER")] = rec.get("VATCODE")
                        try:
                            account_code = int(rec.get("NUMBER")[:3])
                        except ValueError, TypeError:
                            _logger.warning(
                                "%s is not a valid account number for %s.",
                                rec.get("NUMBER"),
                                rec.get("NAME11"),
                            )
                            account_code = 300
                        for account_type in account_types:
                            if account_code in range(
                                account_type["min"], account_type["max"]
                            ):
                                if rec.get("CENTRALID", "").startswith("C") or rec.get(
                                    "CENTRALID", ""
                                ).startswith("V01"):
                                    data["account_type"] = "asset_receivable"
                                    data["reconcile"] = True
                                    data["non_trade"] = True
                                elif rec.get("CENTRALID", "").startswith(
                                    "S"
                                ) or rec.get("CENTRALID", "").startswith("V03"):
                                    data["account_type"] = "liability_payable"
                                    data["reconcile"] = True
                                    data["non_trade"] = True
                                else:
                                    data["account_type"] = account_type["id"]
                                    data["reconcile"] = False
                                break
                        if not data.get("account_type"):
                            data["account_type"] = "income_other"
                        account_data_list.append(data)
                        rec_number_list.append(rec.get("NUMBER"))
                        journal_centered_list.append(rec.get("CENTRALID"))
                        is_deprecated_list.append(rec.get("ISLOCKED"))

                        if len(account_data_list) % 100 == 0:
                            _logger.info("Advancement: %s", len(account_data_list))
        account_ids = AccountAccount.create(account_data_list)
        for account, rec_number, journal_centred, is_deprecated in zip(
            account_ids,
            rec_number_list,
            journal_centered_list,
            is_deprecated_list,
            strict=True,
        ):
            account_data[rec_number] = account.id
            journal_centred and manage_centralid(account, journal_centred)
            if is_deprecated:
                account_deprecated_ids += account
        return (
            account_data,
            account_central,
            account_deprecated_ids,
            account_tax,
            account_ids,
        )

    def _post_process_account(self, account_data, vatcode_data, account_tax) -> None:
        for account, vat in account_tax.items():
            if vat in vatcode_data:
                self.env["account.account"].browse(account_data[account]).write(
                    {"tax_ids": [(4, vatcode_data[vat])]}
                )

    def _post_process_tax(self, tax_ids, account_deprecated_ids):
        account_deprecated_ids -= tax_ids.repartition_line_ids.filtered(
            lambda l: l.repartition_type == "tax"
        ).account_id
        return account_deprecated_ids

    def _import_journal(self, dbf_records) -> tuple:
        _logger.info("Import Journals")
        journal_types = {
            "0": "purchase",
            "1": "purchase",
            "2": "sale",
            "3": "sale",
            "5": "general",
        }
        journal_data = {}
        journals = self.env["account.journal"]
        AccountJournal = self.env["account.journal"]
        existing_journals = AccountJournal.search(
            AccountJournal._get_domain_company_compatible(self.env.company)
        )
        used_codes = set(existing_journals.mapped("code"))
        processed_records = set()
        existing_journals_by_code = existing_journals.grouped("code")
        code_inc = 0
        for rec in dbf_records:
            if not rec.get("DBKID") or rec.get("DBKID") in processed_records:
                continue
            journal = existing_journals_by_code.get(rec.get("DBKID"), AccountJournal)
            if not journal:
                if rec.get("DBKTYPE") == "4":
                    journal_type = "bank" if "IBAN" in rec.get("DBKOPT") else "cash"
                else:
                    journal_type = journal_types.get(rec.get("DBKTYPE"), "general")
                code = rec.get("DBKID")[:5]
                if code in used_codes:
                    code = rec.get("DBKID")[-5:]
                while code in used_codes and code_inc < 10000:
                    code_inc += 1
                    code = "*%s" % code_inc
                used_codes.add(code)
                data = {
                    "name": rec.get("DBKDESC"),
                    "code": code,
                    "type": journal_type,
                }
                if data["type"] == "sale":
                    data["default_account_id"] = (
                        self.env.company.account_config_id.income_account_id.id
                    )
                if data["type"] == "purchase":
                    data["default_account_id"] = (
                        self.env.company.account_config_id.expense_account_id.id
                    )
                journal = AccountJournal.create(data)
            journal_data[rec.get("DBKID")] = journal.id
            journals += journal
            processed_records.add(rec.get("DBKID"))
        return journal_data, journals

    def _import_move(
        self,
        dbf_records,
        pdffiles,
        account_data,
        account_central,
        journal_data,
        partner_data,
        vatcode_data,
        param_data,
    ) -> tuple:
        _logger.info("Import Moves")
        ResCurrency = self.env["res.currency"]
        self.env["ir.attachment"]
        suspense_account = self.env["account.account"].search(
            [("code", "=", self.suspense_code)], limit=1
        )
        if not self.only_open and not suspense_account:
            raise UserError(
                self.env._(
                    "The code for the Suspense Account you entered doesn't match any account"
                )
            )
        counter_part_created = False
        result = list(
            {
                item
                for item in dbf_records
                if item.get("BOOKYEAR") and item.get("DOCNUMBER") != "99999999"
            }
        )
        grouped = collections.defaultdict(list)
        currency_codes = set()
        for item in result:
            grouped[
                item["DOCNUMBER"],
                item["DBKCODE"],
                item["DBKTYPE"],
                item["BOOKYEAR"],
                item["PERIOD"],
            ] += [item]

            currency_codes.add(item.get("CURRCODE"))
        currencies = ResCurrency.with_context(active_test=False).search(
            [("name", "in", list(currency_codes))]
        )
        if currencies:
            currencies.active = True
        currency_map = {currency.name: currency for currency in currencies}

        move_data_list = []
        pdf_file_list = []
        for key, val in grouped.items():
            journal_id = self.env["account.journal"].browse(journal_data.get(key[1]))
            if not journal_id:
                continue
            bookyear = int(key[3], 36)
            if not bookyear or (
                self.only_open and bookyear not in param_data["openyears"]
            ):
                continue
            perdiod_number = len(param_data["period_date"][bookyear]) - 2
            period = min(int(key[4]), perdiod_number + 1)
            start_period_date = param_data["period_date"][bookyear][period]
            if 1 <= period < perdiod_number:
                end_period_date = param_data["period_date"][bookyear][
                    period + 1
                ] + timedelta(days=-1)
            elif period == perdiod_number:
                end_period_date = param_data["period_date"][bookyear][period + 1]
            else:
                end_period_date = start_period_date
            move_date = val[0].get("DATEDOC")
            move_data_dict = {
                "journal_id": journal_id.id,
                "move_type": "out_invoice"
                if journal_id.type == "sale"
                else "in_invoice"
                if journal_id.type == "purchase"
                else "entry",
                "ref": "%s_%s" % (key[1], key[0]),
                "company_id": self.env.company.id,
                "date": min(max(start_period_date, move_date), end_period_date),
                "payment_state": "not_paid",
            }
            if not move_data_dict.get("journal_id") and key[1] == "MATCHG":
                continue
            move_line_data_list = []
            move_amount_total: float = 0
            move_total_receivable_payable = 0

            tmp_val = []
            for rec in val:
                tmp_val += [rec.copy()]
                if (rec["AMOUNTEUR"] or 0) * (rec["CURRAMOUNT"] or 0) < 0:
                    tmp_val[-1]["CURRAMOUNT"] = 0
                    tmp_val += [rec.copy()]
                    tmp_val[-1]["AMOUNTEUR"] = 0
            val = tmp_val

            for rec in val:
                currency = currency_map.get(rec.get("CURRCODE"))
                partner_id = self.env["res.partner"].browse(
                    partner_data.get(rec.get("ACCOUNTRP"), False)
                )
                account_id = self.env["account.account"].browse(
                    account_data.get(rec.get("ACCOUNTGL"))
                )
                matching_number = (
                    rec.get("MATCHNO")
                    and "%s-%s" % (rec.get("ACCOUNTGL"), rec.get("MATCHNO"))
                ) or False
                balance = rec.get("AMOUNTEUR", 0.0)
                amount_currency = (
                    rec.get("CURRAMOUNT")
                    if currency and rec.get("CURRAMOUNT")
                    else balance
                )
                if balance and not account_id:
                    account_id = suspense_account
                line_data = {
                    "date": rec.get("DATE", False),
                    "account_id": account_id.id,
                    "partner_id": partner_id.id,
                    "date_maturity": rec.get("DUEDATE", False),
                    "name": rec.get("COMMENT"),
                    "balance": balance,
                    "amount_currency": amount_currency,
                    "amount_residual_currency": amount_currency,
                    "matching_number": bool(balance)
                    and matching_number
                    and f"I{matching_number}",
                    "winbooks_line_id": rec["DOCORDER"],
                }
                if currency:
                    line_data["currency_id"] = currency.id

                if move_data_dict["move_type"] != "entry":
                    if rec.get("DOCORDER") == "VAT":
                        line_data["display_type"] = "tax"
                    elif account_id and account_id.account_type in (
                        "asset_receivable",
                        "liability_payable",
                    ):
                        line_data["display_type"] = "payment_term"
                    elif rec.get("DBKTYPE") in (CREDIT_NOTE_PURCHASE_CODE, SALE_CODE):
                        line_data["price_unit"] = -amount_currency
                    elif rec.get("DBKTYPE") in (PURCHASE_CODE, CREDIT_NOTE_SALE_CODE):
                        line_data["price_unit"] = amount_currency

                if rec.get("AMOUNTEUR"):
                    move_amount_total = round(move_amount_total, 2) + round(
                        rec.get("AMOUNTEUR"), 2
                    )
                move_line_data_list.append((0, 0, line_data))
                if account_id.account_type in ("asset_receivable", "liability_payable"):
                    move_total_receivable_payable += rec.get("AMOUNTEUR")

            if journal_id.type in ("sale", "purchase"):
                is_refund = (
                    move_total_receivable_payable < 0
                    if journal_id.type == "sale"
                    else move_total_receivable_payable > 0
                )
                if is_refund and key[2] in (PURCHASE_CODE, SALE_CODE):
                    for move_line_data in move_line_data_list:
                        if move_line_data[2].get("price_unit"):
                            move_line_data[2]["price_unit"] = -move_line_data[2][
                                "price_unit"
                            ]
            else:
                is_refund = False

            for line_data, rec in zip(move_line_data_list, val, strict=False):
                if self.env["account.account"].browse(
                    account_data.get(rec.get("ACCOUNTGL"))
                ).account_type in ("asset_receivable", "liability_payable"):
                    continue
                tax_line = self.env["account.tax"].browse(
                    vatcode_data.get(rec.get("VATCODE") or rec.get("VATIMPUT", []))
                )
                if (
                    not tax_line
                    and line_data[2]["account_id"] in account_central.values()
                ):
                    try:
                        counterpart = next(
                            r
                            for r in val
                            if r["AMOUNTEUR"] == -rec["AMOUNTEUR"]
                            and r["DOCORDER"] == "VAT"
                            and r["VATCODE"]
                        )
                        tax_line = self.env["account.tax"].browse(
                            vatcode_data.get(counterpart["VATCODE"])
                        )
                    except StopIteration:
                        pass
                is_vat_account = (
                    self.env.company.country_id.code == "BE"
                    and rec.get("ACCOUNTGL")[:3] in ("411", "451")
                ) or (
                    self.env.company.country_id.code == "LU"
                    and rec.get("ACCOUNTGL")[:4] in ("4614", "4216")
                )
                is_vat = rec.get("DOCORDER") == "VAT" or (
                    move_data_dict["move_type"] == "entry" and is_vat_account
                )
                repartition_line = (
                    is_refund and tax_line.refund_repartition_line_ids
                ) or tax_line.invoice_repartition_line_ids
                repartition_type = "tax" if is_vat else "base"
                line_data[2].update(
                    {
                        "tax_ids": (
                            tax_line and not is_vat and [Command.link(tax_line.id)]
                        )
                        or [],
                        "tax_tag_ids": [
                            Command.set(
                                tax_line._get_repartition_tags(
                                    is_refund, repartition_type
                                ).ids
                            )
                        ],
                        "tax_repartition_line_id": (
                            is_vat
                            and repartition_line.filtered_domain(
                                [
                                    ("repartition_type", "=", repartition_type),
                                    ("account_id", "=", line_data[2]["account_id"]),
                                ]
                            ).id
                        )
                        or False,
                    }
                )
            move_line_data_list = [
                line for line in move_line_data_list if line[2]["account_id"]
            ]

            if move_data_dict["move_type"] != "entry":
                move_data_dict["currency_id"] = currency_map.get(
                    val[0].get("CURRCODE"), self.env.company.currency_id
                ).id
                move_data_dict["partner_id"] = move_line_data_list[0][2]["partner_id"]
                move_data_dict["invoice_date_due"] = move_line_data_list[0][2][
                    "date_maturity"
                ]
                move_data_dict["invoice_date"] = move_line_data_list[0][2]["date"]
                if is_refund:
                    move_data_dict["move_type"] = move_data_dict["move_type"].replace(
                        "invoice", "refund"
                    )

            if move_amount_total:
                if not counter_part_created:
                    _logger.warning(
                        self.env._(
                            "At least one automatic counterpart has been created at import. This is probably an error. Please check entry lines with reference: Counterpart (generated at import from Winbooks)"
                        )
                    )
                counter_part_created = True
                account_id = journal_id.default_account_id
                account_id = account_id or (
                    partner_id.property_account_payable_id
                    if rec.get("DOCTYPE") in ["0", "1"]
                    else partner_id.property_account_receivable_id
                )
                account_id = account_id or suspense_account
                line_data = {
                    "account_id": account_id.id,
                    "date_maturity": rec.get("DUEDATE", False),
                    "name": self.env._(
                        "Counterpart (generated at import from Winbooks)"
                    ),
                    "balance": -move_amount_total,
                    "amount_currency": -move_amount_total,
                    "price_unit": abs(move_amount_total),
                }
                move_line_data_list.append((0, 0, line_data))

            if (
                move_data_dict["move_type"] != "entry"
                and len(move_line_data_list) == 1
                and move_line_data_list[0][2].get("display_type") == "payment_term"
                and move_line_data_list[0][2]["balance"] == 0
            ):
                line_data = {
                    "account_id": journal_id.default_account_id.id,
                    "name": self.env._(
                        "Counterpart (generated at import from Winbooks)"
                    ),
                    "balance": 0,
                }
                move_line_data_list.append((0, 0, line_data))

            move_data_dict["line_ids"] = move_line_data_list
            attachment_key = "%s_%s_%s" % (key[1], key[4], key[0])
            pdf_files = {
                name: fd for name, fd in pdffiles.items() if attachment_key in name
            }
            pdf_file_list.append(pdf_files)
            move_data_list.append(move_data_dict)

            if len(move_data_list) % 100 == 0:
                _logger.info("Advancement: %s", len(move_data_list))

        _logger.info("Creating moves")
        move_ids = (
            self.env["account.move"]
            .with_context(skip_invoice_sync=True)
            .create(move_data_list)
        )
        _logger.info("Creating attachments")
        attachment_data_list = []
        for move, pdf_files in zip(move_ids, pdf_file_list, strict=True):
            if pdf_files:
                for name, fd in pdf_files.items():
                    attachment_data = {
                        "name": name.split("/")[-1],
                        "type": "binary",
                        "datas": base64.b64encode(fd.read()),
                        "res_model": move._name,
                        "res_id": move.id,
                        "res_name": move.name,
                    }
                    attachment_data_list.append(attachment_data)
        self.env["ir.attachment"].create(attachment_data_list)
        return {f"{m.date.year}_{m.ref}": m for m in move_ids}, move_ids

    def _import_analytic_account(self, dbf_records, param_data) -> tuple:
        _logger.info("Import Analytic Accounts")
        analytic_account_data = {}
        analytic_plan_dict = {}
        analytic_accounts = self.env["account.analytic.account"]
        AccountAnalyticAccount = self.env["account.analytic.account"]
        AccountAnalyticPlan = self.env["account.analytic.plan"]
        for rec in dbf_records:
            if not rec.get("NUMBER"):
                continue
            analytic_account = AccountAnalyticAccount.search(
                [
                    ("code", "=", rec.get("NUMBER")),
                    ("company_id", "=", self.env.company.id),
                ],
                limit=1,
            )
            plan_name = param_data["ZONANA" + rec["TYPE"]]
            if not analytic_plan_dict.get(plan_name):
                analytic_plan_dict[plan_name] = AccountAnalyticPlan.search(
                    [("name", "=", plan_name)], limit=1
                ) or AccountAnalyticPlan.create({"name": plan_name})
            if not analytic_account:
                data = {
                    "code": rec.get("NUMBER"),
                    "name": rec.get("NAME1"),
                    "active": not rec.get("INVISIBLE"),
                    "plan_id": analytic_plan_dict[plan_name].id,
                }
                analytic_account = AccountAnalyticAccount.create(data)
            analytic_accounts += analytic_account
            analytic_account_data[rec["NUMBER"]] = analytic_account
        return analytic_account_data, analytic_accounts

    def _import_analytic_account_line(
        self, dbf_records, analytic_account_data, account_data, move_data, param_data
    ):
        _logger.info("Import Analytic Account Lines")
        analytic_line_data_list = []
        analytic_list = None
        line2analytics2amount = collections.defaultdict(
            lambda: collections.defaultdict(float)
        )
        first_move_line_by_key = {}
        for line in self.env["account.move"].union(*move_data.values()).line_ids:
            first_move_line_by_key.setdefault(
                (
                    line.move_id,
                    line.winbooks_line_id,
                    line.account_id.id,
                    round(line.balance, 1),
                ),
                line,
            )
        for rec in dbf_records:
            bookyear = int(rec["BOOKYEAR"] or "0", 36)
            if not bookyear or (
                self.only_open and bookyear not in param_data["openyears"]
            ):
                continue
            if not analytic_list:
                analytic_list = [k for k in rec if "ZONANA" in k]
            bookyear_first_year = param_data["period_date"][int(rec["BOOKYEAR"], 36)][
                0
            ].year
            bookyear_last_year = param_data["period_date"][int(rec["BOOKYEAR"], 36)][
                -1
            ].year
            journal_code, move_number = rec["DBKCODE"], rec["DOCNUMBER"]
            account_id = account_data.get(rec.get("ACCOUNTGL"))
            analytic_accounts = [
                analytic_account_data.get(rec[analytic])
                for analytic in analytic_list
                if analytic_account_data.get(rec.get(analytic))
            ]
            move = move_data.get(
                f"{bookyear_first_year}_{journal_code}_{move_number}"
            ) or move_data.get(f"{bookyear_last_year}_{journal_code}_{move_number}")
            if move:
                move_line = first_move_line_by_key.get(
                    (
                        move,
                        rec["DOCORDER"],
                        account_id,
                        round(rec.get("AMOUNTGL"), 1),
                    ),
                    self.env["account.move.line"],
                )
                line2analytics2amount[move_line][
                    ",".join(str(a.id) for a in analytic_accounts)
                ] += rec.get("AMOUNTEUR")
            else:
                analytic_line_data_list.append(
                    {
                        "date": rec.get("DATE", False),
                        "name": rec.get("COMMENT"),
                        "amount": -rec.get("AMOUNTEUR"),
                        "general_account_id": account_id,
                        **{
                            account.plan_id._column_name(): account.id
                            for account in analytic_accounts
                        },
                    }
                )
                if len(analytic_line_data_list) % 100 == 0:
                    _logger.info("Advancement: %s", len(analytic_line_data_list))
        if line2analytics2amount or analytic_line_data_list:
            group_user = self.env.ref("base.group_user", raise_if_not_found=False)
            group_analytic = self.env.ref(
                "analytic.group_analytic_accounting", raise_if_not_found=False
            )
            if group_user and group_analytic:
                group_user.sudo()._add_implied_group(group_analytic)
        if line2analytics2amount:
            _logger.info(
                "Updating Analytic Distributions on %s lines",
                len(line2analytics2amount),
            )
            self.env["decimal.precision"].search(
                [("name", "=", "Percentage Analytic")]
            ).digits = 6
            for line, analytics2amount in line2analytics2amount.items():
                line.analytic_distribution = {
                    analytics: 100
                    * (amount / line.balance if amount and line.balance else 1)
                    for analytics, amount in analytics2amount.items()
                }
        if analytic_line_data_list:
            _logger.info("Creating Analytic Lines")
        return self.env["account.analytic.line"].create(analytic_line_data_list)

    def _get_or_create_tax_tags(
        self, codes: str | None, cache: dict[str, AccountAccountTag]
    ) -> AccountAccountTag:
        tags = self.env["account.account.tag"]
        if not codes:
            return tags
        indexes = [i for i, char in enumerate(codes) if char in ("+", "-")] + [
            len(codes)
        ]
        for start, end in itertools.pairwise(indexes):
            name = codes[start + 1 : end]
            tag = cache.get(name)
            if not tag:
                tag = (
                    self.env["account.account.tag"]
                    .with_context(lang="en_US")
                    .search([("name", "=", name), ("applicability", "=", "taxes")])
                )
                if not tag:
                    tag = self.env["account.account.tag"].create(
                        {
                            "name": name,
                            "applicability": "taxes",
                            "country_id": self.env.company.tax_config_id.account_fiscal_country_id.id,
                        }
                    )
                cache[name] = tag
            tags += tag
        return tags

    def _import_vat(self, dbf_records, account_central) -> tuple:
        _logger.info("Import VAT")
        vatcode_data = {}
        treelib = {}
        AccountTax = self.env["account.tax"]
        tags_cache: dict[str, AccountAccountTag] = {}

        data_list = []
        code_list = []
        for rec in sorted(dbf_records, key=lambda rec: len(rec.get("TREELEVEL"))):
            treelib[rec.get("TREELEVEL")] = rec.get("TREELIB1")
            if not rec.get("USRCODE1"):
                continue
            tax_name = " ".join(
                [
                    treelib[x]
                    for x in [
                        rec.get("TREELEVEL")[:i]
                        for i in range(2, len(rec.get("TREELEVEL")) + 1, 2)
                    ]
                ]
            )
            tax = AccountTax.search(
                [
                    ("company_ids", "in", self.env.company.ids),
                    ("name", "=", tax_name),
                    (
                        "type_tax_use",
                        "=",
                        "sale" if rec.get("CODE")[0] == "2" else "purchase",
                    ),
                ],
                limit=1,
            )
            if tax.amount != rec.get("RATE") if rec.get("TAXFORM") else 0.0:
                tax.amount = rec.get("RATE") if rec.get("TAXFORM") else 0.0
            if tax:
                vatcode_data[rec.get("CODE")] = tax.id
            else:
                data = {
                    "amount_type": "percent",
                    "name": tax_name,
                    "company_ids": [Command.set(self.env.company.ids)],
                    "amount": rec.get("RATE") if rec.get("TAXFORM") else 0.0,
                    "type_tax_use": "sale" if rec.get("CODE")[0] == "2" else "purchase",
                    "price_include_override": "tax_excluded"
                    if rec.get("TAXFORM") or rec.get("BASFORM") == "BAL"
                    else "tax_included",
                    "refund_repartition_line_ids": [
                        Command.create(
                            {
                                "repartition_type": "base",
                                "tag_ids": [
                                    Command.link(tag.id)
                                    for tag in self._get_or_create_tax_tags(
                                        rec.get("BASE_CN"), tags_cache
                                    )
                                ],
                            }
                        ),
                        Command.create(
                            {
                                "repartition_type": "tax",
                                "tag_ids": [
                                    Command.link(tag.id)
                                    for tag in self._get_or_create_tax_tags(
                                        rec.get("TAX_CN"), tags_cache
                                    )
                                ],
                                "account_id": account_central.get(
                                    rec.get("ACCCN1"), False
                                ),
                            }
                        ),
                    ],
                    "invoice_repartition_line_ids": [
                        Command.create(
                            {
                                "repartition_type": "base",
                                "tag_ids": [
                                    Command.link(tag.id)
                                    for tag in self._get_or_create_tax_tags(
                                        rec.get("BASE_INV"), tags_cache
                                    )
                                ],
                            }
                        ),
                        Command.create(
                            {
                                "repartition_type": "tax",
                                "tag_ids": [
                                    Command.link(tag.id)
                                    for tag in self._get_or_create_tax_tags(
                                        rec.get("TAX_INV"), tags_cache
                                    )
                                ],
                                "account_id": account_central.get(
                                    rec.get("ACCINV1"), False
                                ),
                            }
                        ),
                    ],
                }
                if rec.get("ACCCN2"):
                    data["refund_repartition_line_ids"] += [
                        Command.create(
                            {
                                "repartition_type": "tax",
                                "factor_percent": -100.0,
                                "tag_ids": [],
                                "account_id": account_central.get(
                                    rec.get("ACCCN2"), False
                                ),
                            }
                        )
                    ]
                if rec.get("ACCINV2"):
                    data["invoice_repartition_line_ids"] += [
                        Command.create(
                            {
                                "repartition_type": "tax",
                                "factor_percent": -100.0,
                                "tag_ids": [],
                                "account_id": account_central.get(
                                    rec.get("ACCINV2"), False
                                ),
                            }
                        )
                    ]
                data_list.append(data)
                code_list.append(rec.get("CODE"))

                if len(data_list) % 100 == 0:
                    _logger.info("Advancement: %s", len(data_list))
        tax_ids = AccountTax.create(data_list)
        for tax_id, code in zip(tax_ids, code_list, strict=True):
            vatcode_data[code] = tax_id.id
        return vatcode_data, tax_ids

    def _import_param(self, dbf_records):

        def parse_csv_value(csv_values):
            return dict(pair.split("=") for pair in csv_values.split(","))

        param_data = {}
        param_data["openyears"] = []
        param_data["period_date"] = {}
        for rec in dbf_records:
            if not rec.get("ID"):
                continue
            rec_id = rec.get("ID")
            value = rec.get("VALUE")
            search = re.search(r"BOOKYEAR(\d+).STATUS", rec_id)
            if search and search.group(1) and value.lower() == "open":
                param_data["openyears"].append(int(search.group(1)))
            search = re.search(r"BOOKYEAR(\d+).PERDATE", rec_id)
            if search and search.group(1):
                param_data["period_date"][int(search.group(1))] = [
                    datetime.strptime(value[i * 8 : (i + 1) * 8], "%d%m%Y").date()
                    for i in range(int(len(value) / 8))
                ]
            try:
                csv_values = parse_csv_value(value + rec.get("VALUEEXT"))
            except ValueError:
                csv_values = {}
            if csv_values.get("NAME", "").startswith("ZONANA"):
                param_data[csv_values["NAME"]] = csv_values["TIT1"]
        return param_data

    def _post_import(self, account_deprecated_ids) -> None:
        account_deprecated_ids.write({"active": False})

    def action_import(self):
        if not self.env.company.country_id:
            action = self.env.ref("base.action_res_company_form")
            raise RedirectWarning(
                self.env._("Please define the country on your company."),
                action.id,
                self.env._("Company Settings"),
            )
        if not self.env.company.account_config_id.chart_template:
            action = self.env.ref("account.action_account_config")
            raise RedirectWarning(
                self.env._("You should install a Fiscal Localization first."),
                action.id,
                self.env._("Accounting Settings"),
            )
        self = self.with_context(active_test=False)
        with TemporaryDirectory() as tmp_dir:
            file_dir = pathlib.Path(tmp_dir)

            def get_dbfrecords(filterfunc):
                return itertools.chain.from_iterable(
                    DBF(
                        file_dir / file, encoding="latin", recfactory=frozendict
                    ).records
                    for file in [s for s in dbffiles if filterfunc(s)]
                )

            with zipfile.ZipFile(
                io.BytesIO(base64.decodebytes(self.zip_file))
            ) as zip_ref:
                sub_zips = [
                    filename
                    for filename in zip_ref.namelist()
                    if filename.lower().endswith(".zip")
                ]
                zip_ref.extractall(file_dir, members=sub_zips)

            try:
                cie_zip_name = next(
                    filename for filename in sub_zips if "@cie@" in filename.lower()
                )
            except StopIteration as e:
                raise UserError(
                    self.env._(
                        "No data zip in the main archive. Please use the complete Winbooks export."
                    )
                ) from e
            with zipfile.ZipFile(file_dir / cie_zip_name, "r") as child_zip_ref:
                dbffiles = [
                    filename
                    for filename in child_zip_ref.namelist()
                    if filename.lower().endswith(".dbf")
                ]
                child_zip_ref.extractall(file_dir, members=dbffiles)

            pdffiles = {}
            scan_zip_names = [
                filename for filename in sub_zips if "@scandbk" in filename.lower()
            ]
            try:
                for scan_zip_name in scan_zip_names:
                    with zipfile.ZipFile(file_dir / scan_zip_name, "r") as scan_zip:
                        _pdffiles = [
                            filename
                            for filename in scan_zip.namelist()
                            if filename.lower().endswith(".pdf")
                        ]
                        scan_zip.extractall(file_dir, members=_pdffiles)
                        for filename in _pdffiles:
                            pdffiles[filename] = (file_dir / filename).open("rb")

                param_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_param.dbf")
                )
                param_data = self._import_param(param_recs)

                dbk_recs = get_dbfrecords(
                    lambda file: "dbk" in file.lower() and file.lower().endswith(".dbf")
                )
                journal_data, journal_ids = self._import_journal(dbk_recs)

                acf_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_acf.dbf")
                )
                (
                    account_data,
                    account_central,
                    account_deprecated_ids,
                    account_tax,
                    account_ids,
                ) = self._import_account(acf_recs)

                vat_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_codevat.dbf")
                )
                vatcode_data, tax_ids = self._import_vat(vat_recs, account_central)

                account_deprecated_ids = self._post_process_tax(
                    tax_ids, account_deprecated_ids
                )
                self._post_process_account(account_data, vatcode_data, account_tax)

                table_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_table.dbf")
                )
                category_data = self._import_partner_info(table_recs)

                csf_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_csf.dbf")
                )
                partner_data, partner_ids = self._import_partner(
                    csf_recs, category_data, account_data
                )

                act_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_act.dbf")
                )
                move_data, move_ids = self._import_move(
                    act_recs,
                    pdffiles,
                    account_data,
                    account_central,
                    journal_data,
                    partner_data,
                    vatcode_data,
                    param_data,
                )

                anf_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_anf.dbf")
                )
                analytic_account_data, analytic_account_ids = (
                    self._import_analytic_account(anf_recs, param_data)
                )

                ant_recs = get_dbfrecords(
                    lambda file: file.lower().endswith("_ant.dbf")
                )
                analytic_account_line_ids = self._import_analytic_account_line(
                    ant_recs, analytic_account_data, account_data, move_data, param_data
                )

                self._post_import(account_deprecated_ids)
                _logger.info("Completed")
                self.env["onboarding.onboarding.step"].sudo().action_validate_step(
                    "account.onboarding_onboarding_step_chart_of_accounts"
                )

                import_summary = self.env["wizard.account.import.summary"].create(
                    {
                        "import_summary_account_ids": account_ids,
                        "import_summary_journal_ids": journal_ids,
                        "import_summary_move_ids": move_ids,
                        "import_summary_partner_ids": partner_ids,
                        "import_summary_tax_ids": tax_ids,
                        "import_summary_analytic_ids": analytic_account_ids,
                        "import_summary_analytic_line_ids": analytic_account_line_ids,
                    }
                )
            finally:
                for fd in pdffiles.values():
                    fd.close()
        return import_summary.action_view_summary_view()
