from odoo import models


class RunnerMachine(models.Model):
    _inherit = "runner.machine"
    _receiver_privileges = ("runner_github.privilege_link_runs",)
