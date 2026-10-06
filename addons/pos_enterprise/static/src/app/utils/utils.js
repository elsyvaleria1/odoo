/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { getColorBrightness } from "@web/core/colors/colors";
import { now } from "@web/core/l10n/dates";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export const computeFontColor = (bgColor) => {
    if (!bgColor) {
        return "black";
    }

    return getColorBrightness(bgColor) > 0.5 ? "black" : "white";
};

export function useDelayedValueChange(getCurrentValue, duration = 5000) {
    const state = proxy({
        oldValue: getCurrentValue(),
    });
    let timeout = null;
    useLayoutEffect(
        () => {
            timeout = setTimeout(() => {
                state.oldValue = getCurrentValue();
            }, duration);
            return () => clearTimeout(timeout);
        },
        () => [getCurrentValue()],
    );
    return {
        get isActive() {
            // Empty ORM notes can be false or ""; preserve the hook's coercive comparison.
            // eslint-disable-next-line eqeqeq
            return state.oldValue != getCurrentValue();
        },
    };
}

export const computeDurationSinceDate = (startDateTime) => {
    const timeDiff = (now().epochMilliseconds - startDateTime.epochMilliseconds) / 1000;
    return Math.floor(timeDiff / 60);
};
