// @ts-check
/** @odoo-module native */

import { Component, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/ui/dialog/confirmation_dialog";

export class FileUploadProgressBar extends Component {
    static template = "web.FileUploadProgressBar";
    static props = { fileUpload: t.object() };
    props = useProps(this.constructor.props);

    /** @type {import("services").ServiceFactories["dialog"]} */
    dialogService;

    setup() {
        this.dialogService = useService("dialog");
    }

    onCancel() {
        if (!this.props.fileUpload.xhr) {
            return;
        }
        this.dialogService.add(ConfirmationDialog, {
            body: _t(
                "Do you really want to cancel the upload of %s?",
                this.props.fileUpload.title,
            ),
            confirm: () => {
                this.props.fileUpload.xhr.abort();
            },
        });
    }
}
