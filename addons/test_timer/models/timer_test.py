from odoo import fields, models


class TimerTest(models.Model):
    """A very simple model only inheriting from mixin.timer to test
    timer features"""

    _name = "timer.test"
    _description = "Timer Model"
    _inherit = ["mixin.timer"]

    name = fields.Char(required=True)


class InterruptionTimerTest(models.Model):
    """A very simple model inheriting from mixin.timer and
    overriding _action_interrupt_user_timers()"""

    _name = "interruption.timer.test"
    _description = "Interruption Timer Model"
    _inherit = ["mixin.timer"]

    def _action_interrupt_user_timers(self):
        self.action_timer_stop()
