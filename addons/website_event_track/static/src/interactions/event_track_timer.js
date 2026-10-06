/** @odoo-module native */
import { formatDuration, now } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { Interaction } from "@web/public/interaction";

export class WebsiteEventTrackTimer extends Interaction {
    static selector = ".o_we_track_timer";

    dynamicContent = {
        ".close": { "t-on-click": this.onCloseClick },
    };

    setup() {
        const timeToLive = parseInt(this.el.dataset.timeToLive);
        const deadline = now().add({ seconds: timeToLive || 0 });
        const remainingMs = deadline.epochMilliseconds - now().epochMilliseconds;
        if (remainingMs > 0) {
            this.updateTimerDisplay(remainingMs);
            this.el.classList.remove("d-none");
            this.deadline = deadline;
            this.timer = setInterval(this.refreshTimer.bind(this), 1000);
        } else {
            this.destroy();
        }
    }

    destroy() {
        this.el.parentNode.remove();
        clearInterval(this.timer);
    }

    onCloseClick() {
        this.destroy();
    }

    refreshTimer() {
        const remainingMs = this.deadline.epochMilliseconds - now().epochMilliseconds;
        if (remainingMs > 0) {
            this.updateTimerDisplay(remainingMs);
        } else {
            this.destroy();
        }
    }

    /**
     * @param {integer} remainingMs
     */
    updateTimerDisplay(remainingMs) {
        const timerTextEl = this.el.querySelector("span");
        const humanDuration = formatDuration(remainingMs / 1000, true);
        const str = _t("in %s", humanDuration);
        if (str !== timerTextEl.textContent) {
            timerTextEl.textContent = str;
        }
    }
}

registry
    .category("public.interactions")
    .add("website_event_track.website_event_track_timer", WebsiteEventTrackTimer);
