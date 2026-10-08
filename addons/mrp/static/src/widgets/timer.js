/** @odoo-module native */
import {
    Component,
    onWillDestroy,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { parseFloatTime } from "@web/core/parsers";
import { registry } from "@web/core/registry";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { useInputField } from "@web/fields/input_field_hook";
import { standardFieldProps } from "@web/fields/standard_field_props";

const LIVE_DURATION_FIELD = "duration_live";

function formatMinutes(value) {
    if (value === false) {
        return "";
    }
    const isNegative = value < 0;
    if (isNegative) {
        value = Math.abs(value);
    }
    let min = Math.floor(value);
    let sec = Math.round((value % 1) * 60);
    if (sec === 60) {
        min += 1;
        sec = 0;
    }
    sec = `${sec}`.padStart(2, "0");
    min = `${min}`.padStart(2, "0");
    return `${isNegative ? "-" : ""}${min}:${sec}`;
}

export class MrpTimer extends Component {
    static template = "mrp.MrpTimer";
    static props = { value: t.number(), ongoing: t.boolean().optional(false) };
    props = useProps(this.constructor.props);

    setup() {
        this.state = proxy({ duration: this.props.value });
        this.value = this.props.value;
        this.ongoing = false;
        onWillStart(() => this._follow(this.props.value, this.props.ongoing));
        onWillUpdateProps((nextProps) =>
            this._follow(nextProps.value, nextProps.ongoing),
        );
        onWillDestroy(() => this._stop());
    }

    get durationFormatted() {
        return formatMinutes(this.state.duration);
    }

    _follow(value, ongoing) {
        if (value !== this.value || (ongoing && !this.ongoing)) {
            this.value = value;
            this.base = value;
            this.startedAt = Date.now();
            this.state.duration = value;
        }
        this.ongoing = ongoing;
        if (!ongoing) {
            this._stop();
        } else if (!this._interval) {
            this._interval = setInterval(() => this._tick(), 1000);
        }
    }

    _tick() {
        this.state.duration = this.base + (Date.now() - this.startedAt) / 60000;
    }

    _stop() {
        clearInterval(this._interval);
        this._interval = undefined;
    }
}

class MrpTimerField extends Component {
    static template = "mrp.MrpTimerField";
    static components = { MrpTimer };
    static props = standardFieldProps;
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.numpadDecimalRef = elementRef();
        useInputField({
            getValue: () => this.durationFormatted,
            ref: this.numpadDecimalRef,
            parse: (v) => parseFloatTime(v),
        });

        this.state = proxy({ duration: this.props.record.data[this.props.name] });
        useRecordObserver(async (record) => {
            this.state.duration = await this.getLiveDuration(record);
        });
    }

    async getLiveDuration(record) {
        if (record.model.useSampleModel || record.data.state !== "progress") {
            return record.data[this.props.name];
        }
        if (LIVE_DURATION_FIELD in record.data) {
            return record.data[LIVE_DURATION_FIELD];
        }
        return this.orm.call("mrp.workorder", "get_duration", [record.resId]);
    }

    get duration() {
        const value = this.props.record.data[this.props.name];
        return this.props.record.dirty ? value : this.state.duration;
    }

    get durationFormatted() {
        return formatMinutes(this.duration);
    }

    get ongoing() {
        return this.props.record.data.is_user_working;
    }
}

export const mrpTimerField = {
    component: MrpTimerField,
    supportedTypes: ["float"],
};

registry.category("fields").add("mrp_timer", mrpTimerField);
registry.category("formatters").add("mrp_timer", formatMinutes);
