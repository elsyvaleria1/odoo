/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useOwnedDialogs } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { formView } from "@web/views/form";
import { FieldSelectorDialog } from "@web_studio/client_action/view_editor/editors/components/field_selector_dialog";
import { StudioHook } from "@web_studio/client_action/view_editor/editors/components/studio_hook_component";
import {
    randomName,
    studioIsVisible,
    useStudioRef,
} from "@web_studio/client_action/view_editor/editors/utils";
import { SelectionContentDialog } from "@web_studio/client_action/view_editor/interactive_editor/field_configuration/selection_content_dialog";
import { NewButtonBoxDialog } from "@web_studio/client_action/view_editor/interactive_editor/properties/button_properties/new_button_box_dialog";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { AddButtonAction } from "../../../interactive_editor/action_button/action_button.js";

/**
 * Overrides and extensions of components used by the FormRenderer
 * As a rule of thumb, elements should be able to handle the props
 * - studioXpath: the xpath to the node in the form's arch to which the component
 *   refers
 * - They generally be clicked on to change their characteristics (in the Sidebar)
 * - The click doesn't trigger default behavior (the view is inert)
 * - They can be draggable (FormLabel referring to a field)
 * - studioIsVisible: all components whether invisible or not, are compiled and rendered
 *   this props allows to toggle the class o_invisible_modifier
 * - They can have studio hooks, that are placeholders for dropping content (new elements, field, or displace elements)
 */

const components = formView.Renderer.components;

/*
 * FormLabel:
 * - Can be draggable if in InnerGroup
 */
export class FormLabel extends components.FormLabel {
    static template = "web_studio.FormLabel";
    static props = {
        ...components.FormLabel.props,
        studioXpath: t.string(),
        studioIsVisible: t.boolean().optional(),
    };
    setup() {
        super.setup();
        this.config = useViewConfig();
        this.rootRefRef = elementRef();
        useStudioRef(this.rootRefRef, this.onClick.bind(this));
    }
    get className() {
        let className = super.className;
        if (!studioIsVisible(this.props)) {
            className += " o_web_studio_show_invisible";
        }
        className += " o-web-studio-editor--element-clickable";
        return className;
    }
    onClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.config.onNodeClicked(this.props.studioXpath);
    }
}

/*
 * Notebook:
 * - Display every page, the elements in the page handle whether they are invisible themselves
 * - Push a droppable hook on every empty page
 * - Can add a new page
 */
export class Notebook extends components.Notebook {
    static template = "web_studio.Notebook.Hook";
    static components = { ...components.Notebook.components, StudioHook };
    static props = {
        ...components.Notebook.props,
        studioIsVisible: t.boolean().optional(),
        studioXpath: t.string(),
    };

    setup() {
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        super.setup();
        this.config = useViewConfig();
    }
    computePages(props) {
        // `web`'s Notebook answers with `{ pages, disabledPages }`; it used to
        // answer with the pages array alone (odoo bf19a83c9ab). Reading the
        // result as an array threw `pages.forEach is not a function` and took
        // every notebook path in the form editor down with it.
        const computed = super.computePages(props);
        computed.pages.forEach((p) => {
            p[1].studioIsVisible = p[1].isVisible;
            p[1].isVisible = p[1].isVisible || this.viewEditorModel.showInvisible;
        });
        return computed;
    }
    onNewPageClicked() {
        const vem = this.viewEditorModel;
        const node = {
            tag: "page",
            attrs: {
                string: _t("New Page"),
                name: randomName("studio_page"),
            },
        };
        vem.doOperation({
            type: "add",
            node,
            target: vem.getFullTarget(this.props.studioXpath),
            position: "inside",
        });
    }
}

export class StatusBarButtons extends components.StatusBarButtons {
    static template = `web_studio.FormViewAddButtonAction`;
    static components = {
        ...components.StatusBarButtons.components,
        AddButtonAction,
    };
}

export class StatusBarFieldHook extends Component {
    static template = "web_studio.AddElementHook";
    static props = { addStatusBar: t.boolean() };
    props = useProps(this.constructor.props);
    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.addDialog = useOwnedDialogs();
    }
    get classNames() {
        return "o_web_studio_statusbar_hook";
    }
    get title() {
        return _t("Add a pipeline status bar");
    }
    onClick() {
        this.addDialog(SelectionContentDialog, {
            defaultChoices: [
                ["status1", _t("First Status")],
                ["status2", _t("Second Status")],
                ["status3", _t("Third Status")],
            ],
            onConfirm: (choices) => {
                const viewEditorModel = this.viewEditorModel;
                if (this.props.addStatusBar) {
                    viewEditorModel.pushOperation({ type: "statusbar" });
                }

                const target = {
                    tag: "header",
                };
                const subViewXpath = viewEditorModel.getSubviewXpath();
                if (subViewXpath) {
                    target.subview_xpath = subViewXpath;
                }

                viewEditorModel.doOperation({
                    type: "add",
                    target,
                    position: "inside",
                    node: {
                        attrs: {
                            widget: "statusbar",
                            options: "{'clickable': '1'}",
                        },
                        field_description: {
                            default_value: true,
                            field_description: _t("Pipeline status bar"),
                            model_name: viewEditorModel.resModel,
                            name: randomName(`x_studio_selection_field`),
                            selection: JSON.stringify(choices),
                            type: "selection",
                        },
                        tag: "field",
                    },
                });
            },
        });
    }
}

export class AvatarHook extends Component {
    static template = "web_studio.AddElementHook";
    static props = { fields: t.object() };
    props = useProps(this.constructor.props);
    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.addDialog = useOwnedDialogs();
    }
    get classNames() {
        return "oe_avatar ms-3 o_web_studio_avatar";
    }
    get title() {
        return _t("Add Picture");
    }
    onClick() {
        const fields = [];
        for (const field of Object.values(this.props.fields)) {
            if (field.type === "binary") {
                fields.push(field);
            }
        }
        this.addDialog(FieldSelectorDialog, {
            fields,
            showNew: true,
            onConfirm: (field) => {
                this.viewEditorModel.doOperation({
                    type: "avatar_image",
                    field,
                });
            },
        });
    }
}

export class ButtonHook extends Component {
    static template = "web_studio.AddElementHook";
    static props = {
        add_buttonbox: t.boolean().optional(),
        studioIsVisible: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.addDialog = useOwnedDialogs();
    }
    get classNames() {
        return "oe_stat_button o_web_studio_button_hook flex-grow-1 flex-lg-grow-0 fa-solid fa-plus-square";
    }
    get tooltip() {
        return _t("Add a button");
    }
    onClick() {
        this.addDialog(NewButtonBoxDialog, {
            model: this.viewEditorModel,
            isAddingButtonBox: Boolean(this.props.add_buttonbox),
        });
    }
}

export class ButtonBox extends components.ButtonBox {
    static template = "web_studio.ButtonBox";
    static components = {};
    static props = {
        ...components.ButtonBox.props,
        studioIsVisible: t.boolean().optional(),
    };

    setup() {
        super.setup();
        this.togglerRef = elementRef();
        this.viewEditorModel = proxy(useCurrentViewEditorModel());
        this.expanded = proxy({ value: false });
    }

    toggle() {
        this.expanded.value = !this.expanded.value;
        this.togglerRef.el.classList.toggle("show", this.expanded.value);
        this.togglerRef.el.ariaExpanded = this.expanded.value;
    }

    isSlotVisible(slot) {
        if (this.viewEditorModel.isEditingSubview) {
            return false;
        }
        return this.viewEditorModel.showInvisible || super.isSlotVisible(slot);
    }
}
