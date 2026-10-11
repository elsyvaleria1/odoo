from datetime import date

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request
from odoo.tools import SQL, format_date
from odoo.tools.pdf import PdfReader

from odoo.addons.accountant_knowledge.controller.main import (
    KnowledgeAuditReportController,
    render_front_cover_pdf,
)
from odoo.addons.survey.controllers.main import Survey


class EsgMetricSurvey(Survey):
    def _check_validity(
        self,
        survey_sudo,
        answer_sudo,
        answer_token,
        ensure_token=True,
        check_partner=True,
    ):
        validity_code = super()._check_validity(
            survey_sudo, answer_sudo, answer_token, ensure_token, check_partner
        )

        if validity_code == "answer_wrong_user" and answer_sudo and check_partner:
            if (
                survey_sudo
                in request.env["esg.metric"]
                .sudo()
                .search([("survey_ids", "!=", False)])
                .survey_ids
            ):
                user_partners = request.env["res.partner"].search(
                    [("user_id", "=", request.env.user.id)]
                )
                partners = user_partners | request.env.user.partner_id
                if (
                    not request.env.user._is_public()
                    and answer_sudo.partner_id in partners
                ):
                    return True
        return validity_code

    def _get_access_data(
        self, survey_token, answer_token, ensure_token=True, check_partner=True
    ):
        survey_sudo, answer_sudo = self._get_from_access_token(
            survey_token, answer_token
        )
        access_data = super()._get_access_data(
            survey_token, answer_token, ensure_token, check_partner
        )

        if (
            survey_sudo
            and answer_sudo
            and access_data.get("validity_code", False) == "answer_deadline"
            and request.env.user.has_group("esg.esg_group_manager")
        ):
            if (
                survey_sudo
                in request.env["esg.metric"]
                .sudo()
                .search([("survey_ids", "!=", False)])
                .survey_ids
            ):
                access_data["can_answer"] = False
                access_data["validity_code"] = True
        return access_data


class EsgCsrdReportController(KnowledgeAuditReportController):
    def _get_payment_terms_data(self, start_date, end_date):
        avg_days_payment = 0
        pct_payment_on_terms = 0
        reconciled_payments = (
            request.env["account.move"]
            .sudo()
            .search(
                [
                    ("state", "=", "posted"),
                    (
                        "move_type",
                        "in",
                        request.env["account.move"].get_purchase_types(
                            include_receipts=True
                        ),
                    ),
                    ("invoice_date", ">=", start_date),
                    ("invoice_date", "<=", end_date),
                ]
            )
            .reconciled_payment_ids
        )
        if reconciled_payments:
            request.env.cr.execute(
                SQL(
                    """
                SELECT AVG(latest_payments.diff)
                  FROM (
                    SELECT DISTINCT ON (am.id)
                           (ap.date - am.invoice_date) AS diff
                      FROM account_move__account_payment move_payement_rel
                      JOIN account_move am ON move_payement_rel.invoice_id = am.id
                      JOIN account_payment ap ON move_payement_rel.payment_id = ap.id
                     WHERE ap.id IN %(ids)s
                       AND am.active = TRUE
                     ORDER BY am.id, ap.date DESC
                ) AS latest_payments
                """,
                    ids=tuple(reconciled_payments.ids),
                )
            )
            avg_days_payment = request.env.cr.fetchall()[0][0]

            request.env.cr.execute(
                SQL(
                    """
                SELECT COUNT(ap.id)
                  FROM account_move__account_payment move_payement_rel
                  JOIN account_move am ON move_payement_rel.invoice_id = am.id
                  JOIN account_payment ap ON move_payement_rel.payment_id = ap.id
                 WHERE ap.id IN %(ids)s
                   AND am.invoice_date_due IS NOT NULL
                   AND ap.date <= am.invoice_date_due
                   AND am.active = TRUE
                """,
                    ids=tuple(reconciled_payments.ids),
                )
            )
            pct_payment_on_terms = (
                round(
                    request.env.cr.fetchall()[0][0] / len(reconciled_payments) * 100, 2
                )
                if reconciled_payments
                else 0
            )
        return {
            "avg_days_payment": avg_days_payment,
            "pct_payment_on_terms": pct_payment_on_terms,
        }

    def _get_template_variables(self, article):
        if not (
            request.env.user.has_group("esg.esg_group_manager")
            and (esg_report := article.inherited_esg_report_id)
        ):
            return super()._get_template_variables(article)

        base_year_start_date = 0
        base_year_end_date = 0
        if esg_report.base_year:
            base_year_date = esg_report.company_id.sudo().compute_fiscalyear_dates(
                date(esg_report.base_year, 1, 1)
            )
            base_year_start_date = base_year_date["date_from"]
            base_year_end_date = base_year_date["date_to"]

        payment_terms_data_reporting = self._get_payment_terms_data(
            esg_report.start_date, esg_report.end_date
        )
        avg_days_payment_reporting = payment_terms_data_reporting["avg_days_payment"]
        pct_payment_on_terms_reporting = payment_terms_data_reporting[
            "pct_payment_on_terms"
        ]
        avg_days_payment_base = 0
        pct_payment_on_terms_base = 0
        if esg_report.base_year:
            payment_terms_data_base = self._get_payment_terms_data(
                base_year_start_date, base_year_end_date
            )
            avg_days_payment_base = payment_terms_data_base["avg_days_payment"]
            pct_payment_on_terms_base = payment_terms_data_base["pct_payment_on_terms"]

        variables = {
            "{{ report_name }}": esg_report.title,
            "{{ company_name }}": esg_report.company_id.name,
            "{{ date_start }}": format_date(request.env, esg_report.start_date),
            "{{ date_end }}": format_date(request.env, esg_report.end_date),
            "{{ avg_days_payment_reporting }}": str(
                round(avg_days_payment_reporting, 2)
            ),
            "{{ pct_payment_on_terms_reporting }}": str(
                round(pct_payment_on_terms_reporting, 2)
            ),
            "{{ avg_days_payment_base }}": str(round(avg_days_payment_base, 2))
            if esg_report.base_year
            else "",
            "{{ pct_payment_on_terms_base }}": str(round(pct_payment_on_terms_base, 2))
            if esg_report.base_year
            else "",
        }

        if esg_report.report_type != "csrd":
            report_types_dict = dict(
                esg_report._fields["report_type"]._description_selection(request.env)
            )
            balance_sheet_total = (
                request.env["account.move.line"]
                .sudo()
                ._read_group(
                    domain=[
                        ("parent_state", "=", "posted"),
                        (
                            "account_type",
                            "in",
                            [
                                "asset_receivable",
                                "asset_cash",
                                "asset_current",
                                "asset_non_current",
                                "asset_prepayments",
                            ],
                        ),
                        ("date", ">=", esg_report.start_date),
                        ("date", "<=", esg_report.end_date),
                    ],
                    aggregates=["balance:sum"],
                )
            )
            net_turnover = (
                request.env["account.move.line"]
                .sudo()
                ._read_group(
                    domain=[
                        ("parent_state", "=", "posted"),
                        ("account_type", "in", ["income", "income_other"]),
                        ("date", ">=", esg_report.start_date),
                        ("date", "<=", esg_report.end_date),
                    ],
                    aggregates=["balance:sum"],
                )
            )
            ghg_total = (
                request.env["esg.carbon.emission.report"]
                .sudo()
                ._read_group(
                    domain=[
                        ("esg_emission_factor_id", "!=", False),
                        ("date", ">=", esg_report.start_date),
                        ("date", "<=", esg_report.end_date),
                    ],
                    aggregates=["esg_emissions_value_t:sum"],
                )
            )
            main_market_regions = []
            for country, _count in (
                request.env["account.move"]
                .sudo()
                ._read_group(
                    domain=[
                        ("state", "=", "posted"),
                        (
                            "move_type",
                            "in",
                            request.env["account.move"].get_sale_types(
                                include_receipts=True
                            ),
                        ),
                    ],
                    groupby=["partner_id.country_id"],
                    aggregates=["__count"],
                    order="__count desc",
                    limit=5,
                )
            ):
                if country and country.name not in main_market_regions:
                    main_market_regions.append(country.name)

            undefined = request.env._("[Not Mentioned]")
            variables.update(
                {
                    "{{ reporting_type }}": report_types_dict.get(
                        esg_report.report_type, undefined
                    ),
                    "{{ legal_form }}": esg_report.company_id.company_registry
                    or undefined,
                    "{{ nace_code }}": esg_report.nace_id.complete_name or undefined,
                    "{{ country_of_main_operations }}": esg_report.company_id.country_id.name
                    or undefined,
                    "{{ balance_sheet_total }}": str(balance_sheet_total[0][0])
                    if balance_sheet_total
                    else str(0.0),
                    "{{ net_turnover }}": str(net_turnover[0][0])
                    if net_turnover
                    else str(0.0),
                    "{{ ghg_total }}": str(ghg_total[0][0]) if ghg_total else str(0.0),
                    "{{ ghg_intensity }}": str(
                        round(ghg_total[0][0] / net_turnover[0][0], 5)
                    )
                    if ghg_total and net_turnover and net_turnover[0][0] != 0
                    else str(0.0),
                    "{{ main_market_regions }}": ", ".join(main_market_regions)
                    if main_market_regions
                    else undefined,
                }
            )

        return variables

    def _render_front_cover_pdf(self, article) -> PdfReader:
        if not (
            request.env.user.has_group("esg.esg_group_manager")
            and (esg_report := article.inherited_esg_report_id)
        ):
            return super()._render_front_cover_pdf(article)
        return render_front_cover_pdf(esg_report)

    @http.route(
        '/esg_csrd/article/<model("knowledge.article"):root_article>/esg_report',
        type="http",
        auth="user",
        methods=["GET"],
    )
    def export_esg_article_to_pdf(
        self, root_article, include_pdf_files, include_child_articles, **kwargs
    ):
        if not request.env.user.has_group("esg.esg_group_manager"):
            raise Forbidden
        return super().export_article_to_pdf(
            root_article, include_pdf_files, include_child_articles, **kwargs
        )
