from odoo import models


class ResUsers(models.Model):
    _inherit = "res.users"

    def open_employee_sign_requests(self):
        self.check_singleton()
        contracts = (
            self.sudo()
            .env["hr.version"]
            .search([("employee_id", "in", self.employee_ids.ids)])
        )
        sign_from_contract = contracts.mapped("sign_request_ids")
        sign_from_role = (
            self.env["sign.request.item"]
            .sudo()
            .search(
                [
                    ("partner_id", "=", self.partner_id.id),
                    (
                        "role_id",
                        "=",
                        self.env.ref("hr_sign.sign_item_role_employee_signatory").id,
                    ),
                ]
            )
            .mapped("sign_request_id")
        )
        sign_request_ids = sign_from_contract + sign_from_role
        return self.env["hr.employee"]._get_sign_requests_action(sign_request_ids)
