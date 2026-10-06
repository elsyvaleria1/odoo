/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";

export class QWebPicker extends Component {
    static template = "html_editor.QWebPicker";
    static props = { groups: t.any(), select: t.any() };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ groups: this.props.groups });
    }

    onChange(ev) {
        const [groupIndex, elementIndex] = ev.target.value.split(",");
        this.props.select(this.state.groups[groupIndex][elementIndex].node);
    }
}
