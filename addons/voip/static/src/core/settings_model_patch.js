/** @odoo-module native */
import { fields } from "@mail/core/common/record";
import { Settings } from "@mail/core/common/settings_model";
import { FOREVER } from "@voip/softphone/dnd_selector";
import { compareDates, now, serializeDateTime } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(Settings.prototype, {
    setup() {
        super.setup();
        this.do_not_disturb_until_dt = fields.Datetime({
            onUpdate() {
                clearTimeout(this.resetDoNotDisturbTimeoutId);
                if (
                    !this.do_not_disturb_until_dt ||
                    compareDates(this.do_not_disturb_until_dt, now()) <= 0 ||
                    this.do_not_disturb_until_dt.epochMilliseconds ===
                        FOREVER.epochMilliseconds
                ) {
                    return;
                }
                this.resetDoNotDisturbTimeoutId = setTimeout(() => {
                    this.do_not_disturb_until_dt = null;
                }, this.do_not_disturb_until_dt.epochMilliseconds - now().epochMilliseconds);
            },
        });
        /** @type {number} */
        this.resetDoNotDisturbTimeoutId;
    },

    setVoipDoNotDisturb(minutes) {
        if (minutes === 0) {
            this.do_not_disturb_until_dt = null;
        } else if (minutes === -1) {
            this.do_not_disturb_until_dt = FOREVER;
        } else {
            this.do_not_disturb_until_dt = now().add({ minutes });
        }
        this._saveVoipSettings();
    },

    async _saveVoipSettings() {
        await this.store.env.services.orm.call(
            "res.users.settings",
            "set_res_users_settings",
            [[this.id]],
            {
                new_settings: {
                    do_not_disturb_until_dt: this.do_not_disturb_until_dt
                        ? serializeDateTime(this.do_not_disturb_until_dt)
                        : false,
                },
            },
        );
    },
});
