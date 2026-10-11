from odoo import api, models
from odoo.exceptions import UserError
from odoo.fields import Command


class AccountMove(models.Model):
    _inherit = "account.move"

    def _auto_complete_from_document(self, source) -> bool:
        source.check_access("read")
        if source.template_id:
            self._load_template_data(source.template_id)
            return True
        return super()._auto_complete_from_document(source)

    def _load_template_data(self, template) -> None:
        self.check_singleton()
        template.check_singleton()
        template.check_access("read")
        if self.state != "draft":
            raise UserError(self.env._("Templates can only fill draft documents."))
        if (
            not template.active
            or template.is_payment
            or template.move_type != self.move_type
        ):
            raise UserError(
                self.env._("Choose an active template with the same document type.")
            )
        if template.company_id and template.company_id != self.company_id:
            raise UserError(
                self.env._("Choose a template for this company or all companies.")
            )

        partner = self.partner_id or template.partner_id
        wizard = (
            self.env["wizard.account.move.template.create.move"]
            .with_company(
                self.company_id,
            )
            .new(
                {
                    "template_id": template.id,
                    "partner_id": partner.id,
                    "multicompany_id": self.company_id.id,
                }
            )
        )
        accounts = wizard._get_template_line_accounts(
            template.line_ids.filtered(lambda line: line.display_type == "product"),
            self.company_id,
        )
        commands = [Command.clear()]
        for line in template.line_ids:
            vals = self._prepare_template_move_line_vals(line, self.move_type, partner)
            if line.display_type == "product":
                vals["account_id"] = accounts[line.account_code].id
            commands.append(Command.create(vals))
        if template.partner_id and not self.partner_id:
            self.partner_id = template.partner_id
        if template.ref and not self.ref:
            self.ref = template.ref
        if template.invoice_payment_term_id:
            self.invoice_payment_term_id = template.invoice_payment_term_id
        self.invoice_line_ids = commands
        for line, command in zip(self.invoice_line_ids, commands[1:], strict=True):
            if line.display_type == "product":
                _ = line.name, line.price_unit, line.tax_ids
                values = command[2]
                line.update(
                    {key: values[key] for key in ("name", "price_unit", "tax_ids")}
                )

    @api.model
    def _prepare_template_move_line_vals(self, line, move_type, partner):
        vals = {"name": line.name, "sequence": line.sequence}
        if line.display_type != "product":
            return {**vals, "display_type": line.display_type}
        vals.update(
            {
                "account_id": line.account_id.id,
                "analytic_distribution": line.analytic_distribution,
                "partner_id": line.partner_id.id or partner.id,
            }
        )
        if move_type == "entry":
            vals["balance"] = line.balance
        else:
            vals.update(
                {
                    "product_id": line.product_id.id,
                    "quantity": line.quantity,
                    "price_unit": line.price_unit,
                    "discount": line.discount,
                    "tax_ids": [Command.set(line.tax_ids.ids)],
                }
            )
            if line.product_uom_id:
                vals["product_uom_id"] = line.product_uom_id.id
        return vals

    def _prepare_move_line_from_template(self, template_line):
        self.check_singleton()
        accounts = template_line._resolve_codes_in_company(
            [template_line.account_code],
            self.company_id,
        )
        vals = self._prepare_template_move_line_vals(
            template_line,
            self.move_type,
            self.partner_id,
        )
        vals["account_id"] = accounts.get(
            template_line.account_code,
            self.env["account.account"],
        ).id
        return vals
