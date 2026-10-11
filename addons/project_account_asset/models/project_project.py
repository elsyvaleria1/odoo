from odoo import api, fields, models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    assets_count = fields.Integer(
        string="# Assets",
        compute="_compute_assets_count",
        groups="account.group_account_readonly",
    )

    @api.depends("account_id")
    def _compute_assets_count(self) -> None:
        data = self.env["account.depreciation.board"]._read_group(
            [("analytic_distribution", "in", self.account_id.ids)],
            ["analytic_distribution"],
            ["__count"],
        )
        data = {int(account_id): count for account_id, count in data}
        for project in self:
            project.assets_count = data.get(project.account_id.id, 0)


    def action_view_project_assets(self):
        assets = self.env["account.depreciation.board"].search(
            [("analytic_distribution", "in", self.account_id.ids)],
        )
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "account_depreciation.action_account_asset_form"
        )
        action.update(
            {
                "views": [
                    [
                        self.env.ref("account_depreciation.view_account_asset_tree").id,
                        "list",
                    ],
                    [
                        self.env.ref("account_depreciation.view_account_asset_form").id,
                        "form",
                    ],
                    [
                        self.env.ref(
                            "account_depreciation.view_account_asset_kanban"
                        ).id,
                        "kanban",
                    ],
                ],
                "context": {"default_analytic_distribution": {self.account_id.id: 100}},
                "domain": [("id", "in", assets.ids)],
            }
        )
        if len(assets) == 1:
            action["views"] = [[False, "form"]]
            action["res_id"] = assets[0].id
        return action


    def _get_stat_buttons(self):
        buttons = super()._get_stat_buttons()
        if self.env.user.has_group("account.group_account_readonly"):
            buttons.append(
                {
                    "icon": "pencil-square-o",
                    "text": self.env._("Assets"),
                    "number": self.assets_count,
                    "action_type": "object",
                    "action": "action_view_project_assets",
                    "show": self.assets_count > 0,
                    "sequence": 40,
                }
            )
        return buttons
