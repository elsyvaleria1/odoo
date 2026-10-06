from odoo import models


class ProjectProject(models.Model):
    _name = "project.project"
    _inherit = "project.project"

    def web_gantt_write(self, data):
        # If it's schedule context (a project doesn't have a date) we need to
        # remove m2o fields like user_id from the values if they are empty, to
        # keep the old values.
        #
        # Decided per record, and on a copy of `data`. This used to read
        # `self[0].date` and then write the whole recordset, which made the
        # outcome depend on recordset order rather than on the records: with one
        # dated and one undated project, `(p1 + p2)` kept the empty `user_id`
        # key and `(p2 + p1)` dropped it. `self[0]` also raised IndexError on an
        # empty recordset, and this method is public, so an RPC caller can pass
        # no ids at all. `del data[...]` additionally mutated the caller's dict.
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
