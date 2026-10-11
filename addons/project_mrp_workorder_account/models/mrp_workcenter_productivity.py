from odoo import Command, api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpWorkcenterProductivity(models.Model):
    _inherit = "mrp.workcenter.productivity"

    def _create_analytic_entry(self, previous_duration=0, old_dist=None) -> None:
        self.check_singleton()
        employee_aal = (
            self.workorder_id.employee_analytic_account_line_ids.sudo().filtered(
                lambda line: line.employee_id and line.employee_id == self.employee_id
            )
        )
        distribution_update = old_dist and employee_aal
        if distribution_update:
            old_dist = {k.split(",")[0]: old_dist[k] for k in old_dist}
            account = self.env["account.analytic.account"].browse(
                int(max(old_dist, key=old_dist.get))
            )
            biggest_aal = employee_aal.filtered(
                lambda line: line[account.plan_id._column_name()] == account
            )
            amount = biggest_aal.amount / (old_dist[str(account.id)] / 100)
            duration = biggest_aal.unit_amount
        else:
            duration = (self.duration - round(previous_duration, 2)) / 60.0

            amount = -duration * self.employee_cost

        line_vals = self.env["account.analytic.account"]._perform_analytic_distribution(
            self.workorder_id.production_id.project_id.sudo()._get_analytic_distribution(),
            amount,
            duration,
            employee_aal,
            self,
            not distribution_update,
        )
        _debug.logic(
            "workorder_analytic_entry",
            productivity=self.id,
            workorder=self.workorder_id.id,
            by="distribution_update" if distribution_update else "duration_delta",
            amount=amount,
            duration=duration,
            lines=len(line_vals),
        )
        if line_vals:
            self.workorder_id.sudo().employee_analytic_account_line_ids = [
                Command.create(line_val) for line_val in line_vals
            ]

    def unlink(self):
        for time in self:
            time._create_analytic_entry(2 * time.duration)
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        work_center_productivities = super().create(vals_list)
        for work_order, productivities in (
            work_center_productivities.sudo().grouped("workorder_id").items()
        ):
            if (
                work_order.production_id.project_id.sudo()._get_analytic_distribution()
                or work_order.employee_analytic_account_line_ids
            ):
                for productivity in productivities:
                    productivity._create_analytic_entry()
        return work_center_productivities

    def write(self, vals):
        previous_duration_per_productivity = {
            productivity: productivity.duration for productivity in self
        }
        res = super().write(vals)
        if {"date_start", "date_end"} & vals.keys():
            for work_order, productivities in (
                self.sudo().grouped("workorder_id").items()
            ):
                if (
                    work_order.production_id.project_id._get_analytic_distribution()
                    or work_order.employee_analytic_account_line_ids
                ):
                    for productivity in productivities:
                        productivity._create_analytic_entry(
                            previous_duration_per_productivity[productivity]
                        )
        return res
