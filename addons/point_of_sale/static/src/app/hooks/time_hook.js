/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { formatValue, now } from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export function useTime() {
    const state = proxy({ hours: "", day: "", date: "" });
    const timeFormat = localization.timeFormat;
    const dateFormat = localization.dateFormat
        .replace(/MM/g, "LLLL")
        .replace(/\/yy$/, "/yyyy")
        .replace(/[^a-zA-Z]+/g, ", ");
    function setTime() {
        const dateNow = now();
        state.hours = formatValue(dateNow, timeFormat);
        state.day = formatValue(dateNow, "cccc");
        state.date = formatValue(dateNow, dateFormat);
    }
    useLayoutEffect(
        () => {
            const interval = setInterval(() => setTime(), 500);

            return () => {
                clearInterval(interval);
            };
        },
        () => [],
    );
    setTime();
    return state;
}
