/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useAutofocus } from "@web/core/utils/hooks";

export class SubtaskCreate extends Component {
    static template = "project.SubtaskCreate";
    static props = {
        name: t.string(),
        onSubtaskCreateNameChanged: t.function(),
        onBlur: t.function(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.placeholder = _t("Write a task name");
        this.state = proxy({
            name: this.props.name,
            isFieldInvalid: false,
        });
        this.input = elementRef();
        useAutofocus({ ref: this.input });
    }

    /**
     * @private
     * @param {FocusEvent} ev
     */
    _onBlur(ev) {
        if (ev.relatedTarget?.closest(".subtask_create_input")) {
            return;
        }
        this.props.onBlur();
    }

    /**
     * @private
     * @param {InputEvent} ev
     */
    _onInput(ev) {
        const value = ev.target.value;
        this.state.name = value;
        this.state.isFieldInvalid = false;
    }

    _onClick() {
        this.input.el.focus();
    }

    /**
     * @private
     * @param {InputEvent} ev
     */
    _onNameChanged(ev) {
        const value = ev.target.value.trim();
        if (value !== "") {
            this.props.onSubtaskCreateNameChanged(value);
            ev.target.blur();
        }
    }

    _onSaveClick() {
        if (this.input.el.value.trim() === "") {
            this.props.onSubtaskCreateNameChanged(this.input.el.value.trim());
            this.state.isFieldInvalid = true;
            this.state.name = "";
        }
    }
}
