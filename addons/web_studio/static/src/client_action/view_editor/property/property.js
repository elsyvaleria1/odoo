/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { CheckBox } from "@web/components/checkbox";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog";
import { SelectMenu } from "@web/components/select_menu";
import { useDebugMode } from "@web/core/debug/debug_context";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class Property extends Component {
    static template = "web_studio.Property";
    static components = { CheckBox, SelectMenu, DomainSelectorDialog };
    static props = {
        name: t.string(),
        type: t.string(),
        value: t.any().optional(),
        onChange: t.function().optional(),
        childProps: t.object().optional({}),
        class: t.string().optional(""),
        isReadonly: t.boolean().optional(),
        slots: t.object().optional(),
        tooltip: t.string().optional(),
        inputAttributes: t.object().optional(),
        autofocus: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.dialog = useService("dialog");
        this.rootRef = elementRef();

        useLayoutEffect(
            (el) => {
                if (!this.props.autofocus || !el) {
                    return;
                }
                if (this.props.type === "selection") {
                    el.querySelector(".o_select_menu_toggler").click();
                } else {
                    el.querySelector("input").focus();
                }
            },
            () => [this.rootRef.el, this.viewEditorModel.activeNodeXpath],
        );
    }

    get className() {
        const propsClass = this.props.class ? this.props.class : "";
        return `o_web_studio_property_${this.props.name} ${propsClass}`;
    }

    onDomainClicked() {
        this.dialog.add(DomainSelectorDialog, {
            resModel: this.props.childProps.relation,
            domain: this.props.value || "[]",
            isDebugMode: !!this.debug,
            onConfirm: (domain) => this.props.onChange(domain, this.props.name),
        });
    }

    onViewOptionChange(value) {
        this.props.onChange(value, this.props.name);
    }
}
