// @ts-check
/** @odoo-module native */
import { Discuss } from "@mail/core/public_web/discuss";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { patch } from "@web/core/utils/patch";
import { useViewConfig } from "@web/core/view_config_hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
Object.assign(Discuss.components, { ControlPanel });

patch(Discuss.prototype, {
    setup() {
        super.setup();
        this.config = useViewConfig();
        useLayoutEffect(
            /** @param {string|undefined} threadName */
            (threadName) => {
                if (threadName) {
                    this.config?.setDisplayName(threadName);
                }
            },
            () => [this.thread?.displayName],
        );
    },
});
