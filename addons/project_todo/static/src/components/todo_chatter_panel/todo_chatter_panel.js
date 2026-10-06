/** @odoo-module native */
import { WebChatter } from "@mail/chatter/web/web_chatter";
import { Component, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets";

export class TodoChatterPanel extends Component {
    static template = "project_todo.TodoChatterPanel";
    static components = { Chatter: WebChatter };
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        this.bus = useEventBus();
        this.ui = useService("ui");
        this.state = proxy({
            displayChatter: this.ui.isSmall,
        });
        this.rootRef = elementRef();
        useBus(this.bus, "TODO:TOGGLE_CHATTER", this.toggleChatter.bind(this));
    }

    toggleChatter(ev) {
        this.state.displayChatter = ev.detail.displayChatter;
        this.rootRef.el?.parentElement?.classList.toggle(
            "d-none",
            !this.state.displayChatter,
        );
    }
}

export const todoChatterPanel = {
    component: TodoChatterPanel,
    additionalClasses: [
        "o_todo_chatter",
        "d-none",
        "position-relative",
        "p-0",
        "overflow-y-auto",
    ],
};

registry.category("view_widgets").add("todo_chatter_panel", todoChatterPanel);
