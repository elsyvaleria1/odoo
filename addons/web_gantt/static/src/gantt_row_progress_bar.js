/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { hasTouch, isMobileOS } from "@web/core/browser/feature_detection";

export class GanttRowProgressBar extends Component {
    static props = {
        reactive: t.object({ hoveredRowId: t.or([t.string(), t.literal(null)]) }),
        rowId: t.string(),
        progressBar: t.object({
            max_value: t.number(),
            max_value_formatted: t.string(),
            ratio: t.number(),
            value_formatted: t.string(),
            warning: t.string().optional(),
        }),
    };
    static template = "web_gantt.GanttRowProgressBar";
    props = useProps(this.constructor.props);

    get show() {
        const { reactive, rowId } = this.props;
        return reactive.hoveredRowId === rowId || isMobileOS() || hasTouch();
    }

    get status() {
        const { ratio } = this.props.progressBar;
        return ratio > 100 ? "danger" : ratio > 0 ? "success" : null;
    }
}
