import logging

from odoo import Command, api, models

from odoo.addons.account.models.chart_template import TAX_TAG_DELIMITER, template

_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    def _post_load_data(self, template_code, company, template_data):
        super()._post_load_data(template_code, company, template_data)
        self._load_payroll_accounts(template_code, company)

    def _load_payroll_accounts(self, template_code, companies) -> None:
        config_method = getattr(
            self, f"_configure_payroll_account_{template_code}", None
        )
        if config_method:
            config_method(companies)

    @api.model
    def _configure_payroll_account(
        self,
        companies,
        country_code,
        account_codes=None,
        rules_mapping=None,
        default_account=None,
    ) -> None:
        account_codes = account_codes or []
        rules_mapping = rules_mapping or {}
        if not companies:
            return
        if len(companies) > 1 and any(
            "debit_tags" in mapping or "credit_tags" in mapping
            for mapping in rules_mapping.values()
        ):
            raise ValueError(
                "_configure_payroll_account: debit_tag_ids/credit_tag_ids are "
                "not company-dependent and cannot be safely configured for "
                "more than one company in a single call."
            )
        structures = self.env["hr.payroll.structure"].search(
            [("country_id.code", "=", country_code)]
        )
        if not structures:
            return
        AccountAccount = self.env["account.account"]
        rule_tag_mapper = self._get_tag_mapper(
            self.env["res.country"].search([("code", "=", country_code)]).id
        )
        for company in companies:
            company_template = self.with_company(company)

            if company.country_id.code in ["BE", "CH"]:
                company.batch_payroll_move_lines = True
            accounts = {}
            for code in account_codes:
                account = AccountAccount.with_company(company).search(
                    [
                        *AccountAccount._get_domain_company_compatible(company),
                        ("code", "=like", "%s%%" % code),
                    ],
                    limit=1,
                )
                if not account:
                    _logger.warning("Payroll configuration: Missing account %s", code)
                accounts[code] = account

            journal = company_template.ref("hr_payroll_account_journal")
            if not journal.default_account_id and default_account:
                journal.default_account_id = accounts.get(
                    default_account, AccountAccount
                ).id
            structures_by_company = structures.with_company(company)
            structures_by_company.filtered(
                lambda structure: not structure.journal_id
            ).journal_id = journal

            for rule, rule_mapping in rules_mapping.items():
                vals = {}
                if "credit" in rule_mapping:
                    vals["account_credit"] = accounts.get(
                        rule_mapping["credit"], AccountAccount
                    ).id
                if "debit" in rule_mapping:
                    vals["account_debit"] = accounts.get(
                        rule_mapping["debit"], AccountAccount
                    ).id
                if "debit_tags" in rule_mapping:
                    vals["debit_tag_ids"] = [
                        Command.set(
                            rule_tag_mapper(
                                *rule_mapping["debit_tags"].split(TAX_TAG_DELIMITER)
                            )
                        )
                    ]
                if "credit_tags" in rule_mapping:
                    vals["credit_tag_ids"] = [
                        Command.set(
                            rule_tag_mapper(
                                *rule_mapping["credit_tags"].split(TAX_TAG_DELIMITER)
                            )
                        )
                    ]
                if vals:
                    rule.with_company(company).write(vals)

    @template(model="account.journal")
    def _get_payroll_account_journal(self, template_code) -> dict:
        return {
            "hr_payroll_account_journal": {
                "name": self.env._("Salaries"),
                "code": self.env._("SLR"),
                "type": "general",
                "sequence": 99,
            },
        }

    @template(model="hr.payroll.structure")
    def _get_payroll_structure(self, template_code) -> dict:
        return {
            "hr_payroll.structure_002": {
                "journal_id": "hr_payroll_account_journal",
            },
            "hr_payroll.structure_worker_001": {
                "journal_id": "hr_payroll_account_journal",
            },
            "hr_payroll.default_structure": {
                "journal_id": "hr_payroll_account_journal",
            },
        }

    def _prepare_demo_data(self, company=False):
        demo_data = super()._prepare_demo_data(company)
        if not self.env["account.account"].search_count(
            [
                *self.env["account.account"]._get_domain_company_compatible(company),
                ("code", "=", "123456"),
            ],
            limit=1,
        ):
            account_data = demo_data.setdefault("account.account", {})
            account_data["hr_payslip_account"] = {
                "name": self.env._("Account Payslip Houserental"),
                "code": "123456",
                "account_type": "liability_payable",
                "reconcile": True,
            }
        if self.env.ref(
            "hr_payroll.hr_salary_rule_houserentallowance1", raise_if_not_found=False
        ) and self.ref("hr_payslip_account", raise_if_not_found=False):
            demo_data["hr.salary.rule"] = {
                "hr_payroll.hr_salary_rule_houserentallowance1": {
                    "account_debit": "hr_payslip_account",
                    "account_credit": "hr_payslip_account",
                }
            }
        if self.env.ref(
            "hr_payroll.structure_003", raise_if_not_found=False
        ) and self.ref("hr_payroll_account_journal", raise_if_not_found=False):
            demo_data["hr.payroll.structure"] = {
                "hr_payroll.structure_003": {
                    "journal_id": "hr_payroll_account_journal",
                }
            }

        return demo_data
