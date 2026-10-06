/** @odoo-module native */
import { proxy, t } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { formView } from "@web/views/form";
import { FieldStudio } from "@web_studio/client_action/view_editor/editors/components/field_studio";
import { StudioHook } from "@web_studio/client_action/view_editor/editors/components/studio_hook_component";
import { ViewButtonStudio } from "@web_studio/client_action/view_editor/editors/components/view_button_studio";
import { WidgetStudio } from "@web_studio/client_action/view_editor/editors/components/widget_studio";
import * as formEditorRendererComponents from "@web_studio/client_action/view_editor/editors/form/form_editor_renderer/form_editor_renderer_components";
import { AddButtonAction } from "@web_studio/client_action/view_editor/interactive_editor/action_button/action_button";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { ChatterContainer, ChatterContainerHook } from "../chatter_container.js";
import { InnerGroup, OuterGroup } from "./form_editor_groups.js";

class Setting extends formView.Renderer.components.Setting {
    static props = {
        ...formView.Renderer.components.Setting.props,
        studioXpath: t.string().optional(),
        studioIsVisible: t.boolean().optional(),
    };
}
export class FormEditorRenderer extends formView.Renderer {
    static components = {
        ...formView.Renderer.components,
        ...formEditorRendererComponents,
        Field: FieldStudio,
        Widget: WidgetStudio,
        ViewButton: ViewButtonStudio,
        ChatterContainerHook,
        InnerGroup,
        OuterGroup,
        StudioHook,
        Setting,
        AddButtonAction,
    };
    setup() {
        super.setup();
        this.viewConfig = useViewConfig();
        const rootRef = (this.rootRefRef = elementRef());
        this.rootRef = rootRef;
        const viewEditorModel = useCurrentViewEditorModel();
        this.viewEditorModel = proxy(viewEditorModel);
        this.mailComponents.Chatter = ChatterContainer;

        // Deals with invisible modifier by reacting to config.studioShowVisible.
        useLayoutEffect(
            (rootEl, showInvisible) => {
                if (!rootEl) {
                    return;
                }
                rootEl.classList.add("o_web_studio_form_view_editor");
                if (showInvisible) {
                    rootEl
                        .querySelectorAll(
                            ":not(.o-mail-Form-chatter) .o_invisible_modifier",
                        )
                        .forEach((el) => {
                            el.classList.add("o_web_studio_show_invisible");
                            el.classList.remove("o_invisible_modifier");
                        });
                } else {
                    rootEl
                        .querySelectorAll(
                            ":not(.o-mail-Form-chatter) .o_web_studio_show_invisible",
                        )
                        .forEach((el) => {
                            el.classList.remove("o_web_studio_show_invisible");
                            el.classList.add("o_invisible_modifier");
                        });
                }
            },
            () => [rootRef.el, viewEditorModel.showInvisible],
        );

        // do this in another way?
        useLayoutEffect(
            (rootEl) => {
                if (rootEl) {
                    const optCols = rootEl.querySelectorAll(
                        "i.o_optional_columns_dropdown_toggle",
                    );
                    for (const col of optCols) {
                        col.classList.add("text-muted");
                    }
                }
            },
            () => [rootRef.el],
        );
    }
}
