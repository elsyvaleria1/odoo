/** @odoo-module native */
import { useApprovalContext } from "@approval/views/approval_context";
import { onWillUpdateProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { patch } from "@web/core/utils/patch";
import {
    provideViewButtonContext,
    useViewButtonContext,
} from "@web/core/view_button_context_hooks";
import { ViewButton } from "@web/views/view_button";

import { trace } from "../../common/approval_trace.js";
import { ApprovalButton } from "./approval_button.js";
import { useApprovalButton } from "./approval_button_hook.js";

patch(ViewButton.prototype, {
    setup() {
        super.setup(...arguments);
        this.approvalContext = useApprovalContext();
        this.viewButtonContext = useViewButtonContext();
        const { name, type } = this.props.clickParams || {};
        const kind = (type || "").replace(/=$/, "");
        if (!this.props.record && this.props.list) {
            this._gateSelection(name, kind);
            return;
        }
        const model = this.props.record?.resModel;
        // Every button of every row reaches this line, so it stays silent: the
        // ungated case is the common one and says nothing a reader needs.
        if (!name || !model || !this._isApprovalGated()) {
            return;
        }
        if (kind !== "object" && kind !== "action") {
            trace.event("button", "kind_not_gated", { name, model, kind });
            return;
        }
        trace.event("button", "gating", { name, model, kind });
        this.approvalGate = useApprovalButton({
            getRecord: () => this.props.record,
            method: kind === "object" && name,
            action: kind === "action" && name,
        });
        onWillUpdateProps((nextProps) => {
            if (nextProps.record !== this.props.record) {
                // a pager step hands this button the next record: ask about that one
                this.approvalGate.load(nextProps.record);
            }
        });
        // A button stopped by its approvals warns and stays on the record, whatever
        // its kind. A window action has nothing on the server to refuse it, so it is
        // always asked; an object button is gated where it runs as well, so it is
        // asked only while its loaded approvals say it is gated.
        const onClickViewButton = this.viewButtonContext.onClickViewButton;
        provideViewButtonContext({
            onClickViewButton: (params) =>
                onClickViewButton({
                    ...params,
                    beforeExecute: async () => {
                        if (
                            params.beforeExecute &&
                            (await params.beforeExecute()) === false
                        ) {
                            return false;
                        }
                        if (kind === "object" && !this.approvalGate.result?.gated) {
                            trace.event("button", "server_gates_it", {
                                name,
                                model,
                                loaded: Boolean(this.approvalGate.result),
                            });
                            return true;
                        }
                        return this.approvalGate.check();
                    },
                }),
        });
        this.viewButtonContext = useViewButtonContext();
    },

    /**
     * A list header's window action runs on the selection, with nothing on the
     * server to refuse it: it is checked on every selected record first, and runs
     * once all are approved. An object button is gated where it runs.
     *
     * @param {string} name
     * @param {string} kind
     */
    _gateSelection(name, kind) {
        const list = this.props.list;
        if (
            kind !== "action" ||
            !this.approvalContext.approvalGatedModels?.[list.resModel]
        ) {
            return;
        }
        const orm = useService("orm");
        const notification = useService("notification");
        const onClickViewButton = this.viewButtonContext.onClickViewButton;
        provideViewButtonContext({
            onClickViewButton: (params) =>
                onClickViewButton({
                    ...params,
                    beforeExecute: async () => {
                        if (
                            params.beforeExecute &&
                            (await params.beforeExecute()) === false
                        ) {
                            return false;
                        }
                        const { approved } = await orm.call(
                            "approval.binding",
                            "check_button_approval",
                            [list.resModel, await list.getResIds(true), false, name],
                        );
                        if (!approved) {
                            notification.add(
                                _t("This needs an approval before it can run."),
                                { type: "warning" },
                            );
                        }
                        return approved;
                    },
                }),
        });
        this.viewButtonContext = useViewButtonContext();
    },

    /**
     * Whether this button's record belongs to a model with approval bindings. An
     * editor that draws every button's approvals, as Studio's does, overrides it.
     */
    _isApprovalGated() {
        return Boolean(
            this.approvalContext.approvalGatedModels?.[this.props.record.resModel],
        );
    },
});

ViewButton.components = { ...ViewButton.components, ApprovalButton };
