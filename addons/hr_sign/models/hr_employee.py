from collections import defaultdict

from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    sign_request_ids = fields.Many2many(
        comodel_name="sign.request",
        string="Requested Signatures",
        groups="hr.group_hr_user",
    )
    sign_request_count = fields.Integer(
        compute="_compute_sign_request_count",
        classification="hr.compensation",
        groups="hr.group_hr_manager",
    )

    def _compute_sign_request_count(self) -> None:
        contracts = (
            self.env["hr.version"].sudo().search([("employee_id", "in", self.ids)])
        )
        contracts_by_employee = defaultdict(lambda: self.env["sign.request"])
        for contract in contracts:
            contracts_by_employee[contract.employee_id.id] |= contract.sign_request_ids

        partner_ids = self.user_id.partner_id | self.partner_id
        role_items = (
            self.env["sign.request.item"]
            .sudo()
            .search(
                [
                    ("partner_id", "in", partner_ids.ids),
                    (
                        "role_id",
                        "=",
                        self.env.ref("hr_sign.sign_item_role_employee_signatory").id,
                    ),
                ]
            )
            if partner_ids
            else self.env["sign.request.item"]
        )
        requests_by_partner = defaultdict(lambda: self.env["sign.request"])
        for item in role_items:
            requests_by_partner[item.partner_id.id] |= item.sign_request_id

        for employee in self:
            sign_from_contract = contracts_by_employee[employee.id]
            employee_partner_ids = employee.user_id.partner_id | employee.partner_id
            sign_from_role = self.env["sign.request"]
            for partner_id in employee_partner_ids.ids:
                sign_from_role |= requests_by_partner[partner_id]
            employee.sign_request_count = len(
                set(sign_from_contract + sign_from_role + employee.sign_request_ids)
            )

    def open_employee_sign_requests(self):
        self.check_singleton()
        contracts = (
            self.env["hr.version"].sudo().search([("employee_id", "=", self.id)])
        )
        sign_from_contract = contracts.mapped("sign_request_ids")
        sign_from_role = self.env["sign.request"]
        partner_ids = self.user_id.partner_id | self.partner_id
        if partner_ids:
            sign_from_role = (
                self.env["sign.request.item"]
                .sudo()
                .search(
                    [
                        ("partner_id", "in", partner_ids.ids),
                        (
                            "role_id",
                            "=",
                            self.env.ref(
                                "hr_sign.sign_item_role_employee_signatory"
                            ).id,
                        ),
                    ]
                )
                .mapped("sign_request_id")
            )
        sign_request_ids = sign_from_contract + sign_from_role + self.sign_request_ids
        return self._get_sign_requests_action(sign_request_ids)

    def _get_sign_requests_action(self, sign_request_ids):
        if len(sign_request_ids.ids) == 1:
            return sign_request_ids.go_to_document()

        if self.env.user.has_group("sign.group_sign_user"):
            view_id = self.env.ref("sign.sign_request_view_kanban").id
        else:
            view_id = self.env.ref("hr_sign.sign_request_employee_view_kanban").id

        return {
            "type": "ir.actions.act_window",
            "name": "Signature Requests",
            "view_mode": "kanban,list",
            "res_model": "sign.request",
            "view_ids": [(view_id, "kanban"), (False, "list")],
            "domain": [("id", "in", sign_request_ids.ids)],
        }

    def _open_sign_document_wizard(self) -> dict:
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Signature Request"),
            "res_model": "wizard.hr.employee.send.sign.request",
            "view_mode": "form",
            "target": "new",
        }
