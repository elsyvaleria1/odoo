from odoo import models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    def web_gantt_write(self, data):
        if not self:
            return True

        empty_m2o_keys = [
            f_name
            for f_name, value in data.items()
            if (
                not value
                and f_name in self._fields
                and self._fields[f_name].type == "many2one"
            )
        ]

        result = True
        for project in self:
            vals = data
            if not project.date and empty_m2o_keys:
                vals = {
                    f_name: value
                    for f_name, value in data.items()
                    if f_name not in empty_m2o_keys
                }
            result = project.write(vals) and result
        return result
