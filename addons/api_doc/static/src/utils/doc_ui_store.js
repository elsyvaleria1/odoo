/** @odoo-module native */
import { proxy, useListener } from "@odoo/owl";
import { defineScope } from "@web/core/scope";

const envScope = defineScope("api_doc/utils/doc_ui_store");

function isSmall() {
    return window.innerWidth < 960;
}

/** @param {{ isSmall: boolean, size: number }} ui */
function provideDocUI(ui) {
    envScope.provide({ ui });
}

/** @returns {{ isSmall: boolean, size: number } | undefined} */
function useParentDocUI() {
    return envScope.use().ui;
}

export function useDocUI() {
    const parentUI = useParentDocUI();
    if (parentUI) {
        return proxy(parentUI);
    }
    const ui = proxy({
        isSmall: isSmall(),
        size: window.innerWidth,
    });

    provideDocUI(ui);
    useListener(window, "resize", () => {
        ui.size = window.innerWidth;
        ui.isSmall = isSmall();
    });

    return ui;
}
