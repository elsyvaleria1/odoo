/** @odoo-module native */
import {
    AttachToMessageMacro,
    UseAsAttachmentMacro,
} from "@knowledge/macros/file_macros";
import { rpc } from "@web/core/network";
import { useService } from "@web/core/utils/hooks";
import { getDataURLFromFile } from "@web/core/utils/urls";

export const MacrosFileMixin = (T, template) =>
    class extends T {
        static template = template;

        setup() {
            super.setup();
            this.actionService = useService("action");
            this.uiService = useService("ui");
            this.knowledgeCommandsService = useService("knowledgeCommandsService");
            this.macrosServices = {
                action: this.actionService,
                dialog: this.dialogService,
                ui: this.uiService,
            };
            this.targetRecordInfo =
                this.knowledgeCommandsService.getCommandsRecordInfo();
        }

        async onClickAttachToMessage() {
            const dataTransfer = new DataTransfer();
            try {
                const response = await window.fetch(this.fileModel.urlRoute);
                const blob = await response.blob();
                const file = new File([blob], this.fileModel.name, {
                    type: blob.type,
                });
                dataTransfer.items.add(file);
            } catch {
                return;
            }
            const macro = new AttachToMessageMacro({
                targetXmlDoc: this.targetRecordInfo.xmlDoc,
                breadcrumbs: this.targetRecordInfo.breadcrumbs,
                data: {
                    dataTransfer: dataTransfer,
                },
                services: this.macrosServices,
            });
            macro.start();
        }

        async onClickUseAsAttachment() {
            let attachment;
            try {
                const response = await window.fetch(this.fileModel.urlRoute);
                const blob = await response.blob();
                const dataURL = await getDataURLFromFile(blob);
                attachment = await rpc("/html_editor/attachment/add_data", {
                    name: this.fileModel.name,
                    data: dataURL.split(",")[1],
                    is_image: false,
                    res_id: this.targetRecordInfo.resId,
                    res_model: this.targetRecordInfo.resModel,
                });
            } catch {
                return;
            }
            if (!attachment) {
                return;
            }
            const macro = new UseAsAttachmentMacro({
                targetXmlDoc: this.targetRecordInfo.xmlDoc,
                breadcrumbs: this.targetRecordInfo.breadcrumbs,
                data: null,
                services: this.macrosServices,
            });
            macro.start();
        }
    };
