/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class GridTimerButtonCell extends Component {
    static template = "timesheet_grid.GridTimerButtonCell";
    static props = {
        hotKey: t.string().optional(),
        row: t.object(),
        addTimeMode: t.boolean(),
        hovered: t.boolean().optional(),
        timerRunning: t.boolean().optional(),
        onTimerClick: t.function(),
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.ui = useService("ui");
    }
}
