// @ts-check
/** @odoo-module native */

import { t } from "@odoo/owl";
import { DomainSelector } from "@web/components/domain_selector/domain_selector";
import { EditorDialog } from "@web/components/editor_dialog/editor_dialog";
import { Domain } from "@web/core/domain";
import { rpc, RPCError } from "@web/core/network/rpc";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";

export class DomainSelectorDialog extends EditorDialog {
    static template = "web.DomainSelectorDialog";
    static components = { ...EditorDialog.components, DomainSelector };
    static props = {
        close: t.function(),
        onConfirm: t.function(),
        resModel: t.string(),
        className: t.string().optional(),
        defaultConnector: t.or([t.literal("&"), t.literal("|")]).optional(),
        domain: t.string(),
        isDebugMode: t.boolean().optional(false),
        readonly: t.boolean().optional(false),
        text: t.string().optional(),
        confirmButtonText: t.string().optional(),
        disableConfirmButton: t.function().optional(),
        discardButtonText: t.string().optional(),
        title: t.string().optional(),
        context: t.object().optional({}),
    };

    /** @returns {string} */
    get initialValue() {
        return this.props.domain;
    }

    /** @returns {string} */
    get invalidMessage() {
        return _t("Domain is invalid. Please correct it");
    }

    get confirmButtonText() {
        return this.props.confirmButtonText || _t("Confirm");
    }

    get dialogTitle() {
        return this.props.title || _t("Domain");
    }

    get disabled() {
        if (this.props.disableConfirmButton) {
            return this.props.disableConfirmButton(this.state.value);
        }
        return false;
    }

    get discardButtonText() {
        return this.props.discardButtonText || _t("Discard");
    }

    get domainSelectorProps() {
        return {
            className: this.props.className,
            resModel: this.props.resModel,
            readonly: this.props.readonly,
            isDebugMode: this.props.isDebugMode,
            defaultConnector: this.props.defaultConnector,
            domain: this.state.value,
            update: (/** @type {string} */ domain) => this.update(domain),
        };
    }

    /** @returns {Promise<boolean>} */
    async isValueValid() {
        let domain;
        try {
            domain = new Domain(this.state.value).toList({
                ...user.context,
                ...this.props.context,
            });
        } catch {
            return false;
        }
        try {
            return await rpc("/web/domain/validate", {
                model: this.props.resModel,
                domain,
            });
        } catch (error) {
            if (
                error instanceof RPCError &&
                error.data?.name === "odoo.exceptions.ValidationError"
            ) {
                return false;
            }
            throw error;
        }
    }
}
