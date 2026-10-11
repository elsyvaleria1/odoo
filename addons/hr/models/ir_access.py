from odoo import api, models


class IrAccess(models.Model):
    _inherit = "ir.access"

    def _access_bind_employees(self) -> list[int]:
        self.env["hr.employee"].flush_model(["user_id"])
        self.env.cr.execute(
            "SELECT id FROM hr_employee WHERE user_id = %s ORDER BY id",
            [self.env.uid],
        )
        return [employee_id for (employee_id,) in self.env.cr.fetchall()]

    def _access_bind_units(self) -> list[int]:
        self.env["hr.employee"].flush_model(["user_id", "active", "current_version_id"])
        self.env["hr.version"].flush_model(["department_id"])
        self.env.cr.execute(
            """
            SELECT DISTINCT version.department_id
              FROM hr_employee employee
              JOIN hr_version version ON version.id = employee.current_version_id
             WHERE employee.user_id = %s
               AND employee.active
               AND version.department_id IS NOT NULL
             ORDER BY 1
            """,
            [self.env.uid],
        )
        return [department_id for (department_id,) in self.env.cr.fetchall()]


EMPLOYEE_BIND_FIELDS = frozenset(
    {"user_id", "active", "company_id", "version_id", "current_version_id"}
)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    @api.model_create_multi
    def create(self, vals_list):
        employees = super().create(vals_list)
        if any(vals.get("user_id") for vals in vals_list):
            self.env.registry.clear_cache()
        return employees

    def write(self, vals):
        result = super().write(vals)
        if EMPLOYEE_BIND_FIELDS & vals.keys() or "department_id" in vals:
            self.env.registry.clear_cache()
        return result

    def unlink(self):
        bound = any(self.mapped("user_id"))
        result = super().unlink()
        if bound:
            self.env.registry.clear_cache()
        return result


class HrVersion(models.Model):
    _inherit = "hr.version"

    def write(self, vals):
        result = super().write(vals)
        if "department_id" in vals:
            self.env.registry.clear_cache()
        return result
