/** @odoo-module native */
import useStore from "../hooks/useStore.js";

import { Component, t, useProps, xml } from "/web/static/lib/owl/owl.es.js";

export class IconButton extends Component {
    static props = { onClick: t.function(), icon: t.string() };

    props = useProps(this.constructor.props);

    setup() {
        this.store = useStore();
    }

    static template = xml`
    <div class="d-flex align-items-center justify-content-center icon-button btn btn-primary" t-translation="off" t-on-click="this.props.onClick">
        <i class="fa" t-att-class="this.props.icon" aria-hidden="true"></i>
    </div>
  `;
}
