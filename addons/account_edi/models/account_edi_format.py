from odoo import api, fields, models
from odoo.tools import html_escape


class AccountEdiFormat(models.Model):
    _name = "account.edi.format"
    _description = "EDI format"

    name = fields.Char()
    code = fields.Char(required=True)

    _unique_code = models.Constraint(
        "unique (code)",
        "This code already exists",
    )


    @api.model_create_multi
    def create(self, vals_list):
        edi_formats = super().create(vals_list)

        if not edi_formats:
            return edi_formats

        if not self.pool.loaded:
            self.pool._delay_compute_edi_format_ids = True
        else:
            journals = self.env["account.journal"].search([])
            journals._compute_edi_format_ids()

        if any(edi_format._is_web_service_required() for edi_format in edi_formats):
            self.env.ref("account_edi.ir_cron_edi_network").active = True

        return edi_formats

    def _register_hook(self):
        if hasattr(self.pool, "_delay_compute_edi_format_ids"):
            del self.pool._delay_compute_edi_format_ids
            journals = self.env["account.journal"].search([])
            journals._compute_edi_format_ids()

        return super()._register_hook()


    def _get_move_applicability(self, move):
        self.check_singleton()

    def _is_web_service_required(self) -> bool:
        self.check_singleton()
        return False

    def _is_compatible_with_journal(self, journal) -> bool:
        self.check_singleton()
        return journal.type == "sale"

    def _is_enabled_by_default_on_journal(self, journal) -> bool:
        return True

    def _check_move_configuration(self, move):
        return []


    def _prepare_invoice_report(self, pdf_writer, edi_document) -> None:
        self.check_singleton()


    @api.model
    def _format_error_message(self, error_title, errors) -> str:
        bullet_list_msg = "".join("<li>%s</li>" % html_escape(msg) for msg in errors)
        return "%s<ul>%s</ul>" % (error_title, bullet_list_msg)
