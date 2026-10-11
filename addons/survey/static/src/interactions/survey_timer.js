/** @odoo-module native */
import { deserializeDateTime, now, parseISO } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { Interaction } from "@web/public/interaction";

export class SurveyTimer extends Interaction {
    static selector = ".o_survey_timer_container .o_survey_timer";

    start() {
        const surveyFormContentEl = document.querySelector(
            ".o_survey_form_content_data",
        );
        const surveySessionManageEl = document.querySelector(
            ".o_survey_session_manage",
        );
        this.timeDifference = null;
        if (surveyFormContentEl) {
            if (surveyFormContentEl.dataset.serverTime) {
                this.timeDifference =
                    now().epochMilliseconds -
                    deserializeDateTime(surveyFormContentEl.dataset.serverTime)
                        .epochMilliseconds;
            }
            this.startTimer(surveyFormContentEl.dataset);
        } else if (surveySessionManageEl) {
            this.addListener(this.el, "start_timer", (ev) => {
                this.startTimer(ev.detail);
            });
        }
    }

    destroy() {
        clearInterval(this.surveyTimerInterval);
    }

    startTimer(timerData) {
        this.timeLimitMinutes = Number(timerData.timeLimitMinutes);
        this.timer = timerData.timer;
        this.surveyTimerInterval = null;
        this.setupTimer();
    }

    setupTimer() {
        this.countDownDate = parseISO(this.timer, "UTC").add({
            minutes: this.timeLimitMinutes,
        });
        if (Math.abs(this.timeDifference) >= 500) {
            this.countDownDate = this.countDownDate.add({
                milliseconds: this.timeDifference,
            });
        }
        if (this.timeLimitMinutes <= 0) {
            this.triggerTimeUp();
        } else {
            this.updateTimer();
            this.surveyTimerInterval = setInterval(this.updateTimer.bind(this), 1000);
        }
    }

    formatTime(time) {
        return time > 9 ? time : "0" + time;
    }

    triggerTimeUp() {
        this.el.dispatchEvent(new Event("time_up"));
    }

    updateTimer() {
        const timeLeft = Math.round(
            (this.countDownDate.epochMilliseconds - now().epochMilliseconds) / 1000,
        );

        if (timeLeft >= 0) {
            const timeLeftMinutes = parseInt(timeLeft / 60);
            const timeLeftSeconds = timeLeft - timeLeftMinutes * 60;
            this.el.textContent =
                this.formatTime(timeLeftMinutes) +
                ":" +
                this.formatTime(timeLeftSeconds);
        } else {
            if (this.surveyTimerInterval) {
                clearInterval(this.surveyTimerInterval);
            }
            this.triggerTimeUp();
        }
    }
}

registry.category("public.interactions").add("survey.SurveyTimer", SurveyTimer);
