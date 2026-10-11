/** @odoo-module native */
import { Component, onError, onMounted, t, toRaw, useProps, xml } from "@odoo/owl";
import { provideActionCallbackRecorders } from "@web/core/action_hook";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { provideViewConfig, useViewConfig } from "@web/core/view_config_hooks";
import { WithSearch } from "@web/search/with_search/with_search";
import { cleanClickedElements } from "@web_studio/client_action/view_editor/editors/utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

class ActiveNodeEffect extends Component {
    static template = xml`<t t-if="false"/>`;
    static props = { getXpath: t.function(), onChange: t.function() };
    props = useProps(this.constructor.props);

    setup() {
        useLayoutEffect(
            (xpath) => this.props.onChange(xpath),
            () => [this.props.getXpath()],
        );
    }
}

export class StudioView extends Component {
    static components = { ActiveNodeEffect, WithSearch };
    static template = xml`
        <div t-att-style="this.style" class="w-100 h-100" t-ref="this.viewRenderer">
            <WithSearch t-props="this.withSearchProps" t-slot-scope="search">
                <t t-component="this.Controller" t-props="Object.assign(this.controllerProps, search)" />
            </WithSearch>
            <ActiveNodeEffect getXpath="() => this.viewEditorModel.activeNodeXpath" onChange.bind="this.onActiveNodeXpath"/>
        </div>
    `;
    static props = null;
    props = useProps(this.constructor.props);
    setup() {
        this.notification = useService("notification");
        this.style = this.props.setOverlay ? "pointer-events: none;" : "";
        this.withSearchProps = {
            resModel: this.props.resModel,
            SearchModel: this.props.SearchModel,
            context: this.props.context,
            domain: this.props.domain,
            globalState: this.props.globalState,
            searchViewArch: this.props.searchViewArch,
            searchViewFields: this.props.searchViewFields,
            irFilters: this.props.searchViewIrFilters,
            display: this.props.display,
            defaultGroupBy: this.props.defaultGroupBy,
        };
        this.viewEditorModel = useCurrentViewEditorModel();
        this.Controller = toRaw(this.viewEditorModel).editorInfo.editor.Controller;

        this.viewRenderer = elementRef();

        this.controllerProps = { ...this.viewEditorModel.controllerProps };
        if (this.viewEditorModel.initialState.activeNodeXpath) {
            onMounted(() => {
                const initialActiveNodeXpath =
                    this.viewEditorModel.initialState.activeNodeXpath;
                this.viewEditorModel.initialState.activeNodeXpath = null;
                this.viewEditorModel.activeNodeXpath = initialActiveNodeXpath;
            });
        }
        const rawModel = toRaw(this.viewEditorModel);
        useLayoutEffect(
            () => {
                rawModel.isInEdition = false;
            },
            () => [rawModel.isInEdition],
        );

        onError((error) => {
            if (rawModel.isInEdition) {
                this.notification.add(
                    _t(
                        "The requested change caused an error in the view. It could be because a field was deleted, but still used somewhere else.",
                    ),
                    {
                        type: "danger",
                    },
                );
                this.viewEditorModel.resetSidebar("view");
                this.viewEditorModel._operations.undo(false);
            } else {
                throw error;
            }
        });

        const config = {
            ...useViewConfig(),
            onNodeClicked: (xpath) => {
                if (this.updateActiveNode({ xpath })) {
                    this.viewEditorModel.activeNodeXpath = xpath;
                }
            },
        };

        if (this.props.autoClick) {
            onMounted(() => this.props.autoClick());
        }

        provideViewConfig(config);
        provideActionCallbackRecorders({
            __beforeLeave__: null,
            __getGlobalState__: null,
            __getLocalState__: null,
            __getContext__: null,
            __getOrderBy__: null,
        });
    }

    onActiveNodeXpath(xpath) {
        if (xpath) {
            this.updateActiveNode({ xpath, resetSidebarOnNotFound: true });
        }
    }

    updateActiveNode({ xpath, resetSidebarOnNotFound = false }) {
        const vem = this.viewEditorModel;
        cleanClickedElements(this.viewRenderer.el);
        const el = this.viewRenderer.el.querySelector(
            `[data-studio-xpath="${xpath}"], [studioxpath="${xpath}"]`,
        );
        if (!el) {
            if (resetSidebarOnNotFound) {
                vem.resetSidebar();
            }
            return false;
        }
        if (vem.editorInfo.editor.styleClickedElement) {
            vem.editorInfo.editor.styleClickedElement(this.viewRenderer, { xpath });
            return true;
        }
        const clickable = el.closest(".o-web-studio-editor--element-clickable");
        if (clickable) {
            clickable.classList.add("o-web-studio-editor--element-clicked");
        }
        return true;
    }
}
