/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { standardFieldProps } from "@web/fields/standard_field_props";

export class TimerToggleButton extends Component {
    static props = { ...standardFieldProps, context: t.object() };
    static template = "timer.ToggleButton";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
    }

    get buttonClass() {
        const layout = this.props.record.data[this.props.name] ? "danger" : "primary";
        return `bg-${layout} text-bg-${layout}`;
    }

    get iconClass() {
        const icon = this.props.record.data[this.props.name] ? "stop" : "play";
        return `fa fa-${icon}-circle`;
    }

    get title() {
        return this.props.record.data[this.props.name] ? _t("Stop") : _t("Start");
    }

    async onClick(ev) {
        const action = this.props.record.data[this.props.name] ? "stop" : "start";
        await this.orm.call(
            this.props.record.resModel,
            `action_timer_${action}`,
            [[this.props.record.resId]],
            { context: this.props.context },
        );
        await this.props.record.model.load();
    }
}
