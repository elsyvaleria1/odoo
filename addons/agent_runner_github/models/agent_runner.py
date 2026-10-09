from odoo import models


class AgentRunner(models.Model):
    _inherit = "agent.runner"
    _receiver_privileges = ("agent_runner_github.privilege_link_runs",)
