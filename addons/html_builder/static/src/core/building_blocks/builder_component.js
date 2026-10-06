/** @odoo-module native */
import { Component, t, useProps, xml } from "@odoo/owl";

import { useDomState } from "../utils.js";

export class BuilderComponent extends Component {
    static template = xml`<t t-if="this.state.isVisible"><t t-call-slot="default"/></t>`;
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = useDomState(
            (editingElement) => ({
                isVisible: !!editingElement,
            }),
            { checkEditingElement: false },
        );
    }
}
