/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";

import {
    basicContainerBuilderComponentProps,
    useActionInfo,
    useBuilderComponent,
    useInputBuilderComponent,
    useInputDebouncedCommit,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderRange extends Component {
    static template = "html_builder.BuilderRange";
    static props = {
        ...basicContainerBuilderComponentProps,
        min: t.number().optional(0),
        max: t.number().optional(100),
        step: t.number().optional(1),
        displayRangeValue: t.boolean().optional(false),
        computedOutput: t.function().optional(),
        unit: t.string().optional(),
    };
    static components = { BuilderComponent };
    props = useProps(this.constructor.props);

    setup() {
        this.info = useActionInfo();
        useBuilderComponent();
        const { state, commit, preview } = useInputBuilderComponent({
            id: this.props.id,
            formatRawValue: this.formatRawValue.bind(this),
            parseDisplayValue: this.parseDisplayValue.bind(this),
        });

        this.inputRef = elementRef();
        this.debouncedCommitValue = useInputDebouncedCommit(this, this.inputRef);

        this.commit = commit;
        this.preview = preview;
        this.state = state;
    }

    formatRawValue(value) {
        if (this.props.unit) {
            value = value.slice(0, -this.props.unit.length);
        }
        return value;
    }

    parseDisplayValue(value) {
        if (this.props.unit) {
            value = `${value}${this.props.unit}`;
        }
        return value;
    }

    onChange(e) {
        const normalizedDisplayValue = this.commit(e.target.value);
        e.target.value = normalizedDisplayValue;
    }

    onInput(e) {
        this.preview(e.target.value);
        if (this.props.displayRangeValue) {
            this.state.value = this.parseDisplayValue(e.target.value);
        }
    }

    onKeydown(e) {
        if (!["ArrowLeft", "ArrowUp", "ArrowDown", "ArrowRight"].includes(e.key)) {
            return;
        }
        e.preventDefault();
        let value = parseFloat(e.target.value);
        if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
            value = Math.max(this.min, value - this.props.step);
        } else {
            value = Math.min(this.max, value + this.props.step);
        }
        e.target.value = value;
        this.onInput(e);
        this.debouncedCommitValue();
    }

    get rangeInputValue() {
        return this.state.value ? this.formatRawValue(this.state.value) : "0";
    }

    get displayValue() {
        let value = this.rangeInputValue;
        if (this.props.computedOutput) {
            value = this.props.computedOutput(value);
        } else if (this.props.unit) {
            value = `${value}${this.props.unit}`;
        }
        return value;
    }

    get className() {
        const baseClasses = "p-0 border-0";
        return this.props.min > this.props.max
            ? `${baseClasses} o_we_inverted_range`
            : baseClasses;
    }

    get min() {
        return this.props.min > this.props.max ? this.props.max : this.props.min;
    }

    get max() {
        return this.props.min > this.props.max ? this.props.min : this.props.max;
    }
}
