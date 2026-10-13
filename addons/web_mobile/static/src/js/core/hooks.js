/** @odoo-module native */
import { onMounted, onPatched, onWillUnmount } from "@odoo/owl";
import ServiceCore from "@web_mobile/js/services/core";

/**
 * @param {function} func
 * @param {function} [shouldEnable]
 */
export function useBackButton(func, shouldEnable) {
    const owner = {};
    let isEnabled = false;

    function enable() {
        ServiceCore.backButtonManager.addListener(owner, func);
        isEnabled = true;
    }

    function disable() {
        ServiceCore.backButtonManager.removeListener(owner);
        isEnabled = false;
    }

    onMounted(() => {
        if (shouldEnable && !shouldEnable()) {
            return;
        }
        enable();
    });

    onPatched(() => {
        if (!shouldEnable) {
            return;
        }
        const shouldBeEnabled = shouldEnable();
        if (shouldBeEnabled && !isEnabled) {
            enable();
        } else if (!shouldBeEnabled && isEnabled) {
            disable();
        }
    });

    onWillUnmount(() => {
        if (isEnabled) {
            disable();
        }
    });
}
