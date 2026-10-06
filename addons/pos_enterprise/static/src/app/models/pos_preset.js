/** @odoo-module native */
import { PosPreset } from "@point_of_sale/app/models/pos_preset";
import { compareDates, now } from "@web/core/l10n/dates";
import { patch } from "@web/core/utils/patch";

patch(PosPreset.prototype, {
    get nextSlot() {
        const availabilities = this.uiState.availabilities || {};
        const dates = Object.keys(availabilities).sort();

        for (const date of dates) {
            const slotTimes = Object.keys(availabilities[date]).sort();
            for (const slotTime of slotTimes) {
                const slot = availabilities[date][slotTime];
                if (compareDates(slot.datetime, now()) > 0) {
                    return slot;
                }
            }
        }
        return null;
    },
});
