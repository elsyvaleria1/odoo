import { fields, models } from "@web/../tests/web_test_helpers";
import { deserializeDateTime, now, serializeDateTime } from "@web/core/l10n/dates";

export class TimerTimer extends models.Model {
    _name = "timer.timer";

    timer_start = fields.Datetime();
    timer_pause = fields.Datetime();
    is_timer_running = fields.Boolean();
    res_model = fields.Char();
    res_id = fields.Integer();
    user_id = fields.Many2one({ relation: "res.users" });

    action_timer_start(resId) {
        if (!this.read(resId, ["timer_start"])[0].timer_start) {
            this.write(resId, {
                timer_start: this.get_server_time(),
            });
        }
    }

    action_timer_stop(resId) {
        const timer = this.read(resId)[0];
        if (timer.timer_start) {
            const dateTimeStart = deserializeDateTime(timer.timer_start);
            const elapsed = now().epochMilliseconds - dateTimeStart.epochMilliseconds;
            const seconds = elapsed < 0 ? undefined : Math.trunc(elapsed / 1000);
            this.write(resId, { timer_start: false, timer_pause: false });
            return seconds / 3600;
        }
    }

    get_server_time() {
        return serializeDateTime(now());
    }
}

export const timerModels = { TimerTimer };
