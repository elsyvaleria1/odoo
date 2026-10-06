/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class DialogWrapper extends Component {
    static template = xml`<div>
        <div class="o_tablet_popups">
            <t t-component="this.props.Component" t-props="this.props.componentProps" />
        </div>
    </div>`;

    static components = { Dialog };

    static props = {
        Component: t.function(),
        componentProps: t.object().optional(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
}
