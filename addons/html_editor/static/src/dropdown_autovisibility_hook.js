/** @odoo-module native */
import { proxy } from "@odoo/owl";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

export function useDropdownAutoVisibility(overlayState, popoverRef) {
    if (!overlayState) {
        return;
    }
    const state = proxy(overlayState);
    useLayoutEffect(
        () => {
            if (popoverRef.el) {
                if (!state.isOverlayVisible) {
                    popoverRef.el.style.visibility = "hidden";
                } else {
                    popoverRef.el.style.visibility = "visible";
                }
            }
        },
        () => [state.isOverlayVisible],
    );
}
