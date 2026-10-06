/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/ui/dialog";

export class GanttPopoverInDialog extends Component {
    static components = { Dialog };
    static props = {
        close: t.any(),
        component: t.any(),
        componentProps: t.any(),
        dialogTitle: t.any(),
    };
    static template = "web_gantt.GanttPopoverInDialog";
    props = useProps(this.constructor.props);
    get componentProps() {
        return { ...this.props.componentProps, close: this.props.close };
    }
}
