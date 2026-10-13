/** @odoo-module native */
import { Dropdown } from "@web/components/dropdown";
import { patch } from "@web/core/utils/patch";

patch(Dropdown.prototype, {
    /** @override */
    popoverCloseOnClickAway(target, activeEl) {
        const currentActiveEl = this.uiService.getActiveElementOf(target);
        return (
            super.popoverCloseOnClickAway(target, activeEl) ||
            (currentActiveEl !== activeEl &&
                activeEl &&
                activeEl.contains(currentActiveEl) &&
                currentActiveEl.dataset.embedded)
        );
    },
});
