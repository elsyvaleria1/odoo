/** @odoo-module native */

import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { FileUploadEvent } from "@web/core/events";
import { deserializeDateTime, formatDateTime } from "@web/core/l10n/dates";
import { download } from "@web/core/network";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useService } from "@web/core/utils/hooks";
import { ConfirmationDialog, Dialog } from "@web/ui/dialog";

export class DocumentsManageVersions extends Component {
    static components = {
        Dialog,
    };
    static props = {
        documentId: t.number(),
        onVersionsChanged: t.function(),
        close: t.function(),
    };
    static template = "document.ManageVersions";
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.documentService = useService("document.document");
        this.fileUploadService = useService("file_upload");
        this.fileInputRef = elementRef();
        this.formatDate = (d) =>
            formatDateTime(deserializeDateTime(d), { format: "HH:mm DDD" });

        this.state = proxy({
            documentName: "",
            accessToken: "",
            userPermission: "",
            versions: [],
        });

        onWillStart(async () => await this.load());
        useBus(this.fileUploadService.bus, FileUploadEvent.LOADED, async (ev) => {
            const uploadedFor = ev.detail.upload.data?.get("document_id");
            if (Number(uploadedFor) !== this.props.documentId) {
                return;
            }
            await this.load();
        });
    }

    async load() {
        const attachmentFields = {
            name: 1,
            create_date: 1,
            mimetype: 1,
            create_uid: { fields: { name: 1 } },
        };
        const documentData = await this.orm.call("document.document", "web_read", [
            this.props.documentId,
            {
                name: 1,
                access_token: 1,
                user_permission: 1,
                attachment_id: { fields: attachmentFields },
                previous_attachment_ids: { fields: attachmentFields },
            },
        ]);

        Object.assign(this.state, {
            documentName: documentData[0].name,
            userPermission: documentData[0].user_permission,
            accessToken: documentData[0].access_token,
            versions: [
                documentData[0].attachment_id,
                ...documentData[0].previous_attachment_ids,
            ],
        });
    }

    get panelTitle() {
        return _t('Manage Versions of "%s"', this.state.documentName);
    }

    onUploadNewVersion() {
        this.fileInputRef.el.click();
    }

    async onReplace(ev) {
        if (!ev.target.files.length) {
            return;
        }
        await this.documentService.uploadDocument(
            ev.target.files,
            this.state.accessToken,
            {
                document_id: this.props.documentId,
            },
        );
        ev.target.value = "";
    }

    async onDownload(attachmentId) {
        await download({
            data: {},
            url: `/web/content/${attachmentId}?download=true`,
        });
    }

    async onRestore(attachmentId) {
        await this.orm.call("document.document", "action_restore_version", [
            this.props.documentId,
            attachmentId,
        ]);
        await Promise.all([this.load(), this.props.onVersionsChanged()]);
    }

    async onDelete(attachmentId) {
        return this.dialog.add(ConfirmationDialog, {
            body: _t("Are you sure you want to delete this attachment?"),
            confirmLabel: _t("Delete"),
            confirm: async () => {
                await this.orm.call("document.document", "action_delete_from_history", [
                    this.props.documentId,
                    attachmentId,
                ]);
                await Promise.all([this.load(), this.props.onVersionsChanged()]);
            },
            cancel: () => {},
        });
    }
}
