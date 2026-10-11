// @ts-check
/** @odoo-module native */

import { Component, proxy, t, useProps } from "@odoo/owl";
import { useDialogContext } from "@web/core/dialog_context_hooks";
import { _t } from "@web/core/translation";
import { useChildRef } from "@web/core/utils/hooks";
import { Dialog } from "@web/ui/dialog/dialog";

export const deleteConfirmationMessage = _t(
    `Ready to make your record disappear into thin air? Are you sure?
It will be gone forever!

Think twice before you click that 'Delete' button!`,
);

export const confirmationDialogProps = {
    close: t.function(),
    title: t
        .customValidator(
            t.any(),
            (/** @type {unknown} */ m) =>
                typeof m === "string" ||
                (typeof m === "object" && typeof m.toString === "function"),
        )
        .optional(_t("Confirmation")),
    body: t.string().optional(),
    confirm: t.function().optional(),
    confirmLabel: t.string().optional(_t("Ok")),
    confirmClass: t.string().optional("btn-primary"),
    cancel: t.function().optional(),
    cancelLabel: t.string().optional(_t("Cancel")),
    dismiss: t.function().optional(),
};

export class ConfirmationDialog extends Component {
    static template = "web.ConfirmationDialog";
    static components = { Dialog };
    static props = confirmationDialogProps;
    props = useProps(this.constructor.props);

    setup() {
        this.dialogContext = useDialogContext();
        this.dialogContext.dialogData.dismiss = () => this.dismiss();
        /** @type {any} */
        this.modalRef = useChildRef();
        this.state = proxy({ isProcess: false });
    }

    async cancel() {
        return this.execButton(this.props.cancel);
    }

    async confirm() {
        return this.execButton(this.props.confirm);
    }

    async dismiss() {
        return this.runButtonOrClose(this.props.dismiss || this.props.cancel);
    }

    /** @param {boolean} disabled */
    setButtonsDisabled(disabled) {
        this.state.isProcess = disabled;
        if (!disabled) {
            return;
        }
        const active = document.activeElement;
        const modal = this.modalRef.el;
        if (modal && active instanceof HTMLElement && modal.contains(active)) {
            modal.focus();
        }
    }

    /**
     * @param {Function} [callback]
     * @returns {Promise<boolean>}
     */
    async runButton(callback) {
        if (this.state.isProcess) {
            return false;
        }
        this.setButtonsDisabled(true);
        if (callback && (await callback()) === false) {
            this.setButtonsDisabled(false);
            return false;
        }
        return true;
    }

    /**
     * @param {Function} [callback]
     * @returns {Promise<boolean>}
     */
    async runButtonOrClose(callback) {
        try {
            return await this.runButton(callback);
        } catch (e) {
            this.props.close();
            throw e;
        }
    }

    /** @param {Function} [callback] */
    async execButton(callback) {
        if (await this.runButtonOrClose(callback)) {
            this.props.close();
        }
    }
}

export const alertDialogProps = {
    ...ConfirmationDialog.props,
    title: ConfirmationDialog.props.title.optional(_t("Alert")),
    contentClass: t.string().optional(),
};

export class AlertDialog extends ConfirmationDialog {
    static template = "web.AlertDialog";
    static props = alertDialogProps;
}
