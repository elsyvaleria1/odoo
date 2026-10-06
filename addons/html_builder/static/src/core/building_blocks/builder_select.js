/** @odoo-module native */
import { provideBuilderContext } from "@html_builder/core/builder_context";
import { Component, onMounted, t, useProps, xml } from "@odoo/owl";
import { Dropdown, useDropdownState } from "@web/components/dropdown";
import { _t } from "@web/core/translation";
import { setElementContent } from "@web/core/utils/dom/html";
import { elementRef } from "@web/core/utils/element_ref";

import {
    basicContainerBuilderComponentProps,
    useApplyVisibility,
    useSelectableComponent,
    useVisibilityObserver,
} from "../utils.js";
import { BuilderComponent } from "./builder_component.js";

export class WithIgnoreItem extends Component {
    static template = xml`<t t-call-slot="default"/>`;
    static props = { slots: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        provideBuilderContext({ ignoreBuilderItem: true });
    }
}

export class BuilderSelect extends Component {
    static template = "html_builder.BuilderSelect";
    static props = {
        ...basicContainerBuilderComponentProps,
        className: t.string().optional(),
        dropdownContainerClass: t.string().optional(),
        disabled: t.boolean().optional(),
        slots: t.object({ default: t.object(), fixedButton: t.object().optional() }),
        dropdownClass: t.string().optional("o-hb-select-dropdown"),
    };
    static components = {
        Dropdown,
        BuilderComponent,
        WithIgnoreItem,
    };
    props = useProps(this.constructor.props);

    setup() {
        this.rootRef = elementRef();
        this.contentRef = elementRef();
        useVisibilityObserver(this.contentRef, useApplyVisibility(this.rootRef));

        this.dropdown = useDropdownState();

        const buttonRef = (this.buttonRef = elementRef());
        let currentLabel;
        const updateCurrentLabel = () => {
            if (!this.props.slots.fixedButton) {
                const newHtml = currentLabel || _t("None");
                if (buttonRef.el && buttonRef.el.innerHTML !== newHtml) {
                    setElementContent(buttonRef.el, newHtml);
                }
            }
        };
        useSelectableComponent(this.props.id, {
            onItemChange(item) {
                currentLabel = item.getLabel();
                updateCurrentLabel();
            },
        });
        onMounted(updateCurrentLabel);
        provideBuilderContext({
            onSelectItem: () => {
                this.dropdown.close();
            },
        });
    }
}
