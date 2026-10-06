from odoo import api, fields, models
from odoo.tools import frozendict


class TimerTimer(models.Model):
    _name = "timer.timer"
    _description = "Timer Module"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    timer_start = fields.Datetime(export_string_translation=False)
    timer_pause = fields.Datetime(
        string="Timer Last Pause",
        export_string_translation=False,
    )
    is_timer_running = fields.Boolean(
        export_string_translation=False,
        compute="_compute_is_timer_running",
    )
    res_model = fields.Char(
        export_string_translation=False,
        required=True,
    )
    res_id = fields.Integer(
        export_string_translation=False,
        required=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        export_string_translation=False,
    )
    parent_res_model = fields.Char(
        string="Parent Document Model",
        export_string_translation=False,
    )
    parent_res_id = fields.Integer(
        string="Parent Document",
        export_string_translation=False,
    )

    _unique_timer = models.Constraint(
        "UNIQUE(res_model, res_id, user_id)",
        "Only one timer occurrence by model, record and user",
    )

    @api.depends("timer_start", "timer_pause")
    def _compute_is_timer_running(self) -> None:
        for record in self:
            record.is_timer_running = record.timer_start and not record.timer_pause

    def _invalidate_timed_records(self, timers) -> None:
        # user_timer_id is computed, not stored, and its related fields
        # (timer_start, timer_pause, is_timer_running) are cached beside it, so
        # the timed record forgets all of them whenever a timer appears or goes.
        for res_model, res_id, parent_model, parent_id in timers:
            self._invalidate_timer_fields(self.env[res_model].browse(res_id))
            if parent_model and parent_id:
                self._invalidate_timer_fields(self.env[parent_model].browse(parent_id))

    @api.model
    def _invalidate_timer_fields(self, records) -> None:
        fields_to_drop = [
            name
            for name, field in records._fields.items()
            if name == "user_timer_id"
            or (field.related and field.related.split(".")[0] == "user_timer_id")
        ]
        if fields_to_drop:
            records.invalidate_model(fields_to_drop)

    @api.model_create_multi
    def create(self, vals_list):
        self._invalidate_timed_records(
            (
                vals["res_model"],
                vals["res_id"],
                vals.get("parent_res_model"),
                vals.get("parent_res_id"),
            )
            for vals in vals_list
        )
        return super().create(vals_list)

    def unlink(self):
        timed = [
            (timer.res_model, timer.res_id, timer.parent_res_model, timer.parent_res_id)
            for timer in self
        ]
        res = super().unlink()
        self._invalidate_timed_records(timed)
        return res

    def action_timer_start(self):
        if not self.timer_start:
            self.write({"timer_start": fields.Datetime.now()})

    def action_timer_stop(self):
        """Stop the timer and return the spent minutes since it started
        :return minutes_spent if the timer is started,
                otherwise return False
        """
        if not self.timer_start:
            return False
        minutes_spent = self._get_minutes_spent()
        self.write({"timer_start": False, "timer_pause": False})
        return minutes_spent

    def _get_minutes_spent(self):
        start_time = self.timer_start
        stop_time = fields.Datetime.now()
        # timer was either running or paused
        if self.timer_pause:
            start_time += stop_time - self.timer_pause
        return (stop_time - start_time).total_seconds() / 60

    def action_timer_pause(self) -> None:
        self.write({"timer_pause": fields.Datetime.now()})

    def action_timer_resume(self) -> None:
        if self.timer_start and self.timer_pause:
            new_start = self.timer_start + (fields.Datetime.now() - self.timer_pause)
            self.write({"timer_start": new_start, "timer_pause": False})

    @api.model
    @api.readonly
    def get_server_time(self):
        """Returns the server time.
        The timer widget needs the server time instead of the client time
        to avoid time desynchronization issues like the timer beginning at 0:00
        and not 23:59 and so on.
        """
        return fields.Datetime.now()

    @api.model
    def _get_timers(self):
        """Get timers from the current user"""
        return self.env["timer.timer"].search([("user_id", "=", self.env.user.id)])

    def _get_related_document(self):
        self.check_singleton()
        return self.env[self.res_model].browse(self.res_id)
