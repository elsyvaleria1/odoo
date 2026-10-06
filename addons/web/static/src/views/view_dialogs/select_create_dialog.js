// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { renderToMarkup } from "@web/core/utils/render";
import { Dialog } from "@web/ui/dialog/dialog";
import { View } from "@web/views/view";

import { FormViewDialog } from "./form_view_dialog.js";

let _defaultNoContentHelp;
function getDefaultNoContentHelp() {
    if (!_defaultNoContentHelp) {
        _defaultNoContentHelp = renderToMarkup(
            "web.SelectCreateDialog.DefaultNoContentHelp",
        );
    }
    return _defaultNoContentHelp;
}

export class SelectCreateDialog extends Component {
    static components = { Dialog, View };
    static template = "web.SelectCreateDialog";
    static props = {
        context: t.object().optional({}),
        domain: t.array().optional([]),
        dynamicFilters: t.array().optional([]),
        resModel: t.string(),
        searchViewId: t.or([t.number(), t.literal(false)]).optional(false),
        multiSelect: t.boolean().optional(true),
        onSelected: t.function().optional(),
        close: t.function().optional(),
        onCreateEdit: t.function().optional(),
        title: t.string().optional(),
        noCreate: t.boolean().optional(),
        onUnselect: t.function().optional(),
        noContentHelp: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    /** @type {any} */
    dialogService;
    /** @type {{ resIds: any[] }} */
    state;

    setup() {
        this.ui = useService("ui");
        this.dialogService = useService("dialog");
        this.state = proxy({ resIds: [] });
        const noContentHelp = this.props.noContentHelp || getDefaultNoContentHelp();
        this.busy = false;
        this.baseViewProps = {
            display: { searchPanel: false },
            noBreadcrumbs: true,
            noContentHelp,
            showButtons: false,
            selectRecord: (resId) => this.select([resId]),
            onSelectionChanged: (resIds) => {
                this.state.resIds = resIds;
            },
        };
    }

    get viewProps() {
        const type = this.ui.isSmall ? "kanban" : "list";
        /** @type {Record<string, any>} */
        const props = {
            loadIrFilters: true,
            ...this.baseViewProps,
            context: this.props.context,
            domain: this.props.domain,
            dynamicFilters: this.props.dynamicFilters,
            readonly: true,
            resModel: this.props.resModel,
            searchViewId: this.props.searchViewId,
            type,
        };
        if (type === "list") {
            props.allowSelectors = this.props.multiSelect;
            props.allowOpenAction = false;
        } else if (type === "kanban") {
            props.forceGlobalClick = true;
        }
        return props;
    }

    /** @param {() => Promise<void>} callback */
    async executeOnceAndClose(callback) {
        if (!this.busy) {
            this.busy = true;
            try {
                await callback();
            } catch (e) {
                this.busy = false;
                throw e;
            }
            this.props.close();
        }
    }

    /** @param {number[]} resIds */
    async select(resIds) {
        if (this.props.onSelected) {
            await this.executeOnceAndClose(() => this.props.onSelected(resIds));
        }
    }

    async unselect() {
        if (this.props.onUnselect) {
            await this.executeOnceAndClose(() => this.props.onUnselect());
        }
    }

    get canUnselect() {
        return this.ui.isSmall && !!this.props.onUnselect;
    }

    async createEditRecord() {
        if (this.props.onCreateEdit) {
            await this.executeOnceAndClose(() => this.props.onCreateEdit());
        } else {
            this.dialogService.add(FormViewDialog, {
                context: this.props.context,
                resModel: this.props.resModel,
                onRecordSaved: (record) =>
                    this.executeOnceAndClose(() =>
                        this.props.onSelected?.([record.resId]),
                    ),
            });
        }
    }
}

registry.category("dialogs").add("select_create", SelectCreateDialog);
