/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";
import { provideViewModel } from "@web/model/model";

export class WithViewModel extends Component {
    static template = xml`<t t-call-slot="default"/>`;
    static props = { model: t.object(), slots: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        provideViewModel(this.props.model);
    }
}
