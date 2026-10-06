/** @odoo-module native */
import "@web/webclient/promote_studio/promote_studio_systray_item";

import { Component, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useEventBus, useService } from "@web/core/utils/hooks";

class StudioSystray extends Component {
    static template = "web_studio.SystrayItem";
    static props = {};
    props = useProps(this.constructor.props);
    setup() {
        this.bus = useEventBus();
        this.hm = useService("home_menu");
        this.studio = useService("studio");
        this.rootRef = elementRef();
        this.isLoading = false;
        this.bus.addEventListener("ACTION_MANAGER:UPDATE", () => {
            this.isLoading = true;
            if (this.rootRef.el) {
                this.rootRef.el.classList.toggle("o_disabled", this.buttonDisabled);
            }
        });
        this.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", (ev) => {
            this.isLoading = false;
            const mode = ev.detail;
            if (mode !== "new" && this.rootRef.el) {
                this.rootRef.el.classList.toggle("o_disabled", this.buttonDisabled);
            }
        });
    }
    get buttonDisabled() {
        return this.isLoading || !this.studio.isStudioEditable();
    }
    _onClick() {
        if (!this.isLoading) {
            this.studio.open();
        }
    }
}

export const systrayItem = {
    Component: StudioSystray,
    isDisplayed: () => user.isSystem,
};

registry.category("systray").remove("PromoteStudioSystrayItem");
registry.category("systray").add("StudioSystrayItem", systrayItem, { sequence: 1 });
