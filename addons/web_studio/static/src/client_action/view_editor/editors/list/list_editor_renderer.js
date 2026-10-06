/** @odoo-module native */
import { observe, proxy } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { useRender } from "@web/core/utils/render_hooks";
import { useThrottleForAnimation } from "@web/core/utils/timing";
import { useViewConfig } from "@web/core/view_config_hooks";
import { listView } from "@web/views/list";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

import { SelectionHeaderButtons } from "../../interactive_editor/action_button/action_button.js";

const colSelectedClass = "o-web-studio-editor--element-clicked";
const colHoverClass = "o-web-studio--col-hovered";

function cleanStyling(mainEl, classNames) {
    mainEl.querySelectorAll(`${classNames.map((c) => `.${c}`)}`).forEach((el) => {
        el.classList.remove(...classNames);
    });
}

export function columnsStyling(mainEl, colSelector, classNames) {
    mainEl.querySelectorAll(`td${colSelector}, th${colSelector}`).forEach((el) => {
        el.classList.add(...classNames);
    });
}

function getSelectableCol(target, colSelector) {
    if (target.closest("button")) {
        return null;
    }
    const colEl = target.closest(`td${colSelector}, th${colSelector}`);
    return colEl;
}

export class ListEditorRenderer extends listView.Renderer {
    static template = "web_studio.ListEditorRenderer";
    static recordRowTemplate = "web_studio.ListEditorRenderer.RecordRow";
    static components = {
        ...listView.Renderer.components,
        SelectionHeaderButtons,
    };
    render = useRender();

    setup() {
        const viewEditorModel = proxy(useCurrentViewEditorModel());
        this.viewEditorModel = observe(viewEditorModel, () => {
            // Re-render when showInvisible changes on the viewEditorModel:
            // onWillRender recomputes allColumns/columns, and our
            // processAllColumns/getActiveColumns overrides read that value.
            this.render();
        });
        super.setup();
        this.debug = useDebugMode();
        this.config = useViewConfig();
        this.onTableHover = useThrottleForAnimation(this.onTableHover.bind(this));

        useLayoutEffect(
            (rootEl) => {
                rootEl.classList.add("o_web_studio_list_view_editor");
            },
            () => [this.rootRef.el],
        );
    }

    getColumnClass(col) {
        let cls = super.getColumnClass(col);
        if (col.studioColumnInvisible) {
            cls += " o_web_studio_show_invisible";
        }
        return cls;
    }

    getCellClass(col, record) {
        let cls = super.getCellClass(col, record);
        if (col.studioColumnInvisible || super.evalInvisible(col.invisible, record)) {
            cls += " o_web_studio_show_invisible";
        }
        return cls;
    }

    getColumnHookData(col, position) {
        let xpath;
        if (!col) {
            return { xpath: "/list", position: "inside" };
        }
        if (col.type === "button_group") {
            if (position === "before") {
                xpath = col.buttons[0].studioXpath;
            } else {
                xpath = col.buttons[col.buttons.length - 1].studioXpath;
            }
        } else {
            xpath = col.studioXpath;
        }
        return {
            xpath,
            position,
        };
    }

    addColsHooks(_cols) {
        const attrs = { width: "4px" };
        const options = {};
        const cols = [];
        let hookId = 0;
        const firstCol = _cols.find((c) => c.optional !== "hide");
        const { xpath, position } = this.getColumnHookData(firstCol, "before");
        cols.push({
            type: "studio_hook",
            position,
            xpath,
            id: `studio_hook_${hookId++}_${(firstCol && firstCol.id) || 0}`,
            attrs,
            options,
        });
        for (const col of _cols) {
            if (col.optional === "hide") {
                continue;
            }
            cols.push(col);
            const { xpath, position } = this.getColumnHookData(col, "after");
            cols.push({
                type: "studio_hook",
                position,
                xpath,
                id: `studio_hook_${hookId++}_${col.id}`,
                attrs,
                options,
            });
        }
        return cols;
    }

    // `columns` and `allColumns` are class fields on the base renderer (own
    // instance properties, define semantics), so a get/set accessor pair here
    // would be silently shadowed. Hook into the two computation methods the
    // base renderer calls in onWillRender instead.
    processAllColumns(allColumns, list) {
        let cols = super.processAllColumns(allColumns, list);
        cols = cols.filter((c) => !c.attrs?.["data-used-by"]);
        if (this.viewEditorModel.showInvisible) {
            cols = cols.map((c) => ({
                ...c,
                optional: false,
                studioColumnInvisible:
                    c.optional === "hide" ||
                    super.evalColumnInvisible(c.column_invisible),
            }));
        }
        return cols;
    }

    getActiveColumns() {
        return this.addColsHooks(super.getActiveColumns());
    }

    evalInvisible(modifier, record) {
        if (this.viewEditorModel.showInvisible) {
            return false;
        }
        return super.evalInvisible(modifier, record);
    }
    evalColumnInvisible(columnInvisible) {
        if (this.viewEditorModel.showInvisible) {
            return false;
        }
        return super.evalColumnInvisible(columnInvisible);
    }

    onTableHover(ev) {
        const table = this.tableRef.el;
        cleanStyling(table, [colHoverClass]);
        if (ev.type !== "mouseover") {
            return;
        }
        const colEl = getSelectableCol(ev.target, "[data-studio-xpath]");
        if (!colEl) {
            return;
        }
        const xpath = colEl.dataset.studioXpath;
        columnsStyling(
            table,
            `[data-studio-xpath='${xpath}']:not(.o_web_studio_hook)`,
            [colHoverClass],
        );
    }

    onTableClicked(ev) {
        ev.stopPropagation();
        ev.preventDefault();
        const table = ev.currentTarget;
        cleanStyling(table, [colSelectedClass]);
        const colEl = getSelectableCol(ev.target, "[data-studio-xpath]");
        if (!colEl) {
            return;
        }
        this.config.onNodeClicked(colEl.dataset.studioXpath);
    }

    makeTooltipButton(button) {
        return JSON.stringify({
            button: {
                string: button.string,
                type: button.clickParams?.type,
                name: button.clickParams?.name,
            },
            debug: true,
        });
    }
}
