/** @odoo-module native */
import { Component, useProps } from "@odoo/owl";
import { useDebugMode } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog";
import { useCurrentViewEditorModel } from "@web_studio/client_action/view_editor/view_editor_model_context";

export class SidebarPropertiesToolbox extends Component {
    static props = {};
    static template = "web_studio.ViewEditor.InteractiveEditorProperties.Toolbox";
    props = useProps(this.constructor.props);

    setup() {
        this.viewEditorModel = useCurrentViewEditorModel();
        this.debug = useDebugMode();
        this.orm = useService("orm");
        this.action = useService("action");
        this.dialog = useService("dialog");
    }

    get node() {
        return this.viewEditorModel.activeNode;
    }

    get nodeType() {
        return this.node.arch.tagName;
    }

    onRemoveFromView() {
        this.dialog.add(ConfirmationDialog, {
            body: _t(
                "Are you sure you want to remove this %s from the view?",
                this.node.humanName.toLowerCase(),
            ),
            confirm: () => this.removeNodeFromArch(),
            cancel: () => {},
        });
    }

    async openFormAction() {
        const resId = await this.orm.searchRead(
            "ir.model.fields",
            [
                ["model", "=", this.viewEditorModel.resModel],
                ["name", "=", this.node.field.name],
            ],
            ["id"],
        );
        return this.action.doAction(
            {
                type: "ir.actions.act_window",
                res_model: "ir.model.fields",
                res_id: resId[0].id,
                views: [[false, "form"]],
                target: "current",
            },
            { clearBreadcrumbs: true },
        );
    }

    removeNodeFromArch(xpath) {
        const target = this.viewEditorModel.getFullTarget(xpath || this.node.xpath);
        const operation = {
            type: "remove",
            target,
        };
        this.viewEditorModel.resetSidebar();
        return this.viewEditorModel.doOperation(operation);
    }
}
