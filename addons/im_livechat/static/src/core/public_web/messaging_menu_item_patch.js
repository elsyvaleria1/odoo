/** @odoo-module native */
import "@mail/discuss/core/public_web/messaging_menu_item_patch";

import { MessagingMenuItem } from "@mail/core/public_web/messaging_menu/messaging_menu_item";
import { proxy } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { now } from "@web/core/l10n/dates";
import { _t } from "@web/core/translation";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";

const UNIT_MS = { days: 24 * 3600 * 1000, hours: 3600 * 1000, minutes: 60 * 1000 };

patch(MessagingMenuItem.prototype, {
    setup() {
        super.setup();
        this.helpClock = proxy({ now: now() });
        useLayoutEffect(
            /** @param {Temporal.ZonedDateTime|undefined} since */
            (since) => {
                if (!since) {
                    return;
                }
                /** @type {number|undefined} */
                let timeout;
                const tick = () => {
                    this.helpClock.now = now();
                    timeout = browser.setTimeout(tick, this.helpTime.msUntilChange);
                };
                tick();
                return () => browser.clearTimeout(timeout);
            },
            () => [this.helpSince],
        );
    },
    /** @returns {Temporal.ZonedDateTime|undefined} */
    get helpSince() {
        const channel = this.channel;
        return channel?.livechat_status === "need_help"
            ? channel.livechat_looking_for_help_since_dt
            : undefined;
    },
    /** @returns {{text: string, tooltip: string, msUntilChange: number}} */
    get helpTime() {
        const since = this.helpSince;
        if (!since) {
            return { text: "", tooltip: "", msUntilChange: UNIT_MS.minutes };
        }
        const elapsed = Math.max(
            0,
            this.helpClock.now.epochMilliseconds - since.epochMilliseconds,
        );
        const unit =
            elapsed >= UNIT_MS.days
                ? "days"
                : elapsed >= UNIT_MS.hours
                  ? "hours"
                  : "minutes";
        const count = Math.floor(elapsed / UNIT_MS[unit]);
        const text =
            unit === "days"
                ? _t("%(days)sd", { days: count })
                : unit === "hours"
                  ? _t("%(hours)sh", { hours: count })
                  : count
                    ? _t("%(minutes)sm", { minutes: count })
                    : _t("< 1m");
        return {
            text,
            tooltip: _t("Looking for help for: %(duration)s", { duration: text }),
            msUntilChange: (count + 1) * UNIT_MS[unit] - elapsed,
        };
    },
});
