/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

import { sendFilesToUploadInput } from "../document_file_uploader/upload_input.js";

export class UploadDropZone extends Component {
    static template = "account.UploadDropZone";
    static props = {
        dragging: t.boolean().optional(),
        visible: t.boolean().optional(),
        hideZone: t.function().optional(() => () => {}),
        dragIcon: t.string().optional(),
        dragText: t.string().optional(),
        dragTitle: t.string().optional(),
        dragCompany: t.string().optional(),
        dragShowCompany: t.boolean().optional(),
        dropZoneTitle: t.string().optional(),
        dropZoneDescription: t.string().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.notificationService = useService("notification");
    }

    onDrop(ev) {
        sendFilesToUploadInput(ev.dataTransfer, {
            scopeEl: ev.target.closest(".o_drop_area")?.parentElement,
            notification: this.notificationService,
        });
        this.props.hideZone();
    }
}
