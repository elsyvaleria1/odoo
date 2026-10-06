/** @odoo-module native */
import { Component, proxy, useProps, xml } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class Counter extends Component {
    static selector = "#wrapwrap h1";
    static template = xml`
        <div class="btn btn-primary" t-on-click="this.increment">
            Counter. Value=<t t-out="this.state.value"/>
        </div>`;
    static props = {};
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ value: 1 });
        this.notification = useService("notification");
    }

    increment(ev) {
        ev.stopPropagation();
        this.state.value++;
        this.notification.add(`Example of a service: ${this.state.value}`);
    }
}
