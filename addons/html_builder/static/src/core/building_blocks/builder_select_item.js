/** @odoo-module native */
import { useBuilderContext } from "@html_builder/core/builder_context";
import { Component, markup, onMounted, t, useProps } from "@odoo/owl";
import { getActiveHotkey } from "@web/core/browser/hotkeys";
import { elementRef } from "@web/core/utils/element_ref";

import {
    clickableBuilderComponentProps,
    useActionInfo,
    useSelectableItemComponent,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class BuilderSelectItem extends Component {
    static template = "html_builder.BuilderSelectItem";
    static props = {
        ...clickableBuilderComponentProps,
        title: t.string().optional(),
        label: t.string().optional(),
        className: t.string().optional(""),
        slots: t.object().optional(),
    };
    static components = { BuilderComponent };
    props = useProps(this.constructor.props);

    setup() {
        this.builderContext = useBuilderContext();
        if (!this.builderContext.selectableContext) {
            throw new Error(
                "BuilderSelectItem must be used inside a BuilderSelect component.",
            );
        }
        this.info = useActionInfo();
        const item = (this.item = elementRef());
        let label = "";
        const getLabel = () => {
            // todo: it's not clear why the item.el?.innerHTML is not set at in
            // some cases. We fallback on a previously set value to circumvent
            // the problem, but it should be investigated.

            label =
                this.props.label ||
                (item.el ? markup(item.el.innerHTML) : "") ||
                label ||
                "";
            return label;
        };

        onMounted(getLabel);

        const { state, operation } = useSelectableItemComponent(this.props.id, {
            getLabel,
        });
        this.state = state;
        this.operation = operation;

        this.onFocusin = this.operation.preview;
        this.onFocusout = this.operation.revert;
    }

    onClick() {
        this.builderContext.onSelectItem();
        this.operation.commit();
        this.removeKeydown?.();
    }
    onKeydown(ev) {
        const hotkey = getActiveHotkey(ev);
        if (hotkey === "escape") {
            this.operation.revert();
            this.removeKeydown?.();
        }
    }
    onPointerEnter() {
        this.operation.preview();
        const _onKeydown = this.onKeydown.bind(this);
        document.addEventListener("keydown", _onKeydown);
        this.removeKeydown = () => document.removeEventListener("keydown", _onKeydown);
    }
    onPointerLeave() {
        this.operation.revert();
        this.removeKeydown();
    }
}
