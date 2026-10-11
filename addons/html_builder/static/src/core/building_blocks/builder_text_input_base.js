/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useForwardRefToParent } from "@web/core/utils/hooks";

import { useActionInfo } from "../utils.js";

export const textInputBasePassthroughProps = {
    action: t.string().optional(),
    placeholder: t.string().optional(),
    title: t.string().optional(),
    style: t.string().optional(),
    tooltip: t.string().optional(),
    classes: t.string().optional(),
    inputClasses: t.string().optional(),
    prefix: t.string().optional(),
};

export class BuilderTextInputBase extends Component {
    static template = "html_builder.BuilderTextInputBase";
    static props = {
        slots: t.object().optional(),
        inputRef: t.function().optional(),
        ...textInputBasePassthroughProps,
        commit: t.function(),
        preview: t.function(),
        onFocus: t.function().optional(),
        onKeydown: t.function().optional(),
        value: t.or([t.string(), t.literal(null)]).optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.isEditing = false;
        this.info = useActionInfo();
        this.inputRefRef = elementRef();
        this.inputRef = useForwardRefToParent("inputRef", this.inputRefRef);
        this.state = proxy({ value: this.props.value });
        onWillUpdateProps((nextProps) => {
            if ("value" in nextProps) {
                this.state.value = this.isEditing
                    ? this.inputRef.el.value
                    : nextProps.value;
            }
        });
    }

    onChange(ev) {
        this.isEditing = false;
        const normalizedDisplayValue = this.props.commit(ev.target.value);
        ev.target.value = normalizedDisplayValue;
    }

    onInput(ev) {
        this.isEditing = true;
        this.props.preview(ev.target.value);
    }

    onFocus(ev) {
        this.props.onFocus?.(ev);
    }

    onKeydown(ev) {
        this.props.onKeydown?.(ev);
    }
}
