/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { elementRef } from "@web/core/utils/element_ref";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useViewConfig } from "@web/core/view_config_hooks";
import { formView } from "@web/views/form";
import { StudioHook } from "@web_studio/client_action/view_editor/editors/components/studio_hook_component";
import { studioIsVisible } from "@web_studio/client_action/view_editor/editors/utils";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

const components = formView.Renderer.components;

function extendGroup(GroupClass) {
    class Group extends GroupClass {
        static props = {
            ...GroupClass.props,
            studioXpath: t.any().optional(),
            studioIsVisible: t.any().optional(),
        };
        static components = { ...GroupClass.components, StudioHook };
        setup() {
            super.setup();
            this.config = useViewConfig();
            this.viewEditorModel = proxy(useCurrentViewEditorModel());
            this.rootRef = elementRef();
        }
        get allClasses() {
            let classes = super.allClasses;
            if (!studioIsVisible(this.props)) {
                classes = `${classes || ""} o_web_studio_show_invisible`;
            }
            if (this.props.studioXpath) {
                classes = `${classes || ""} o-web-studio-editor--element-clickable`;
            }
            return classes;
        }
        _getItems() {
            const items = super._getItems();
            return items.map(([k, v]) => {
                v = Object.assign({}, v);
                v.studioIsVisible = v.isVisible;
                v.isVisible = v.isVisible || this.viewEditorModel.showInvisible;
                if (v.subType === "item_component") {
                    v.props.studioIsVisible = v.studioIsVisible;
                    v.props.studioXpath = v.studioXpath;
                }
                return [k, v];
            });
        }

        onGroupClicked(ev) {
            if (
                ev.target.closest(".o-web-studio-editor--element-clickable") !==
                this.rootRef.el
            ) {
                return;
            }
            this.config.onNodeClicked(this.props.studioXpath);
        }
    }
    return Group;
}

class InnerGroupItemComponent extends Component {
    static template = "web_studio.Form.InnerGroup.ItemComponent";
    static props = {
        cell: t.object(),
        slots: t.object(),
        marginOnSmallScreen: t.string().optional(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.config = useViewConfig();
        const labelRef = (this.labelRefRef = elementRef());
        const fieldRef = (this.fieldRef = elementRef());

        this.labelRef = labelRef;

        useLayoutEffect(
            (studioIsVisible, labelEl, fieldEl) => {
                if (labelEl) {
                    const clickable = labelEl.querySelector(
                        ".o-web-studio-editor--element-clickable",
                    );
                    if (clickable) {
                        clickable.classList.remove(
                            "o-web-studio-editor--element-clickable",
                        );
                    }
                    labelEl.classList.add("o-web-studio-editor--element-clickable");
                    const invisible = labelEl.querySelector(
                        ".o_web_studio_show_invisible",
                    );
                    if (invisible) {
                        invisible.classList.remove("o_web_studio_show_invisible");
                    }
                    labelEl.classList.toggle(
                        "o_web_studio_show_invisible",
                        !studioIsVisible,
                    );
                    labelEl.classList.add("o-draggable");
                }

                if (fieldEl) {
                    const clickable = fieldEl.querySelector(
                        ".o-web-studio-editor--element-clickable",
                    );
                    if (clickable) {
                        clickable.classList.remove(
                            "o-web-studio-editor--element-clickable",
                        );
                    }
                    const invisible = fieldEl.querySelector(
                        ".o_web_studio_show_invisible",
                    );
                    if (invisible) {
                        invisible.classList.remove("o_web_studio_show_invisible");
                    }
                    fieldEl.classList.add("o-web-studio-element-ghost");
                }
            },
            () => [this.cell.studioIsVisible, labelRef.el, fieldRef.el],
        );

        this.onMouseFieldIO = (ev) => {
            labelRef.el.classList.toggle(
                "o-web-studio-ghost-hovered",
                ev.type === "mouseover",
            );
        };
    }
    get cell() {
        return this.props.cell;
    }

    onClicked(ev) {
        if (ev.target.closest(".o-web-studio-element-ghost")) {
            ev.stopPropagation();
        }
        this.config.onNodeClicked(this.cell.studioXpath);
    }
}

const _InnerGroup = extendGroup(components.InnerGroup);
export class InnerGroup extends _InnerGroup {
    static template = "web_studio.Form.InnerGroup";
    getRows() {
        const rows = super.getRows();
        if (!this.viewEditorModel.showInvisible) {
            rows.forEach((row) => {
                row.isVisible = row.some((cell) => cell.studioIsVisible);
            });
        }
        return rows;
    }

    getStudioHooks() {
        const hooks = new Map();
        const rows = this.getRows();
        const hasRows = rows.length >= 1 && rows[0].length;

        if (!hasRows) {
            hooks.set("inside", {
                xpath: this.props.studioXpath,
                position: "inside",
                subTemplate: "formGrid",
                colSpan: this.props.maxCols,
            });
        }

        for (const rowIdx in rows) {
            const row = rows[rowIdx];
            const colSpan = row.reduce((acc, val) => acc + val.itemSpan || 1, 0);
            if (!hooks.has("beforeFirst")) {
                const cell = row[0];
                if (cell) {
                    hooks.set("beforeFirst", {
                        xpath: cell.studioXpath,
                        position: "before",
                        subTemplate: "formGrid",
                        width: cell.width,
                        colSpan,
                    });
                }
            }

            if (
                row.every((cell) => !cell.studioIsVisible) &&
                !this.viewEditorModel.showInvisible
            ) {
                continue;
            }
            const cell = row[row.length - 1];
            if (cell) {
                hooks.set(`afterRow ${rowIdx}`, {
                    xpath: cell.studioXpath,
                    position: "after",
                    subTemplate: "formGrid",
                    width: cell.width,
                    colSpan,
                });
            }
        }
        return hooks;
    }
}

InnerGroup.components.InnerGroupItemComponent = InnerGroupItemComponent;

export const OuterGroup = extendGroup(components.OuterGroup);
OuterGroup.template = "web_studio.Form.OuterGroup";
