/** @odoo-module native */

import { AgentSourceAddDialog } from "@ai/components/agent_add_source_dialog/agent_add_source_dialog";
import { _t } from "@web/core/translation";
import { patch } from "@web/core/utils/patch";
import { SelectCreateDialog } from "@web/views/view_dialogs";

patch(AgentSourceAddDialog.prototype, {
    get cardsData() {
        return [
            ...super.cardsData,
            {
                image: "/ai_document_source/static/img/icon.png",
                icon: "fa-file-text-o",
                title: _t("Add from Documents"),
                onClick: () => this.onAddDocumentsSourceClick(),
            },
        ];
    },

    onAddDocumentsSourceClick() {
        this.dialog.add(SelectCreateDialog, {
            title: _t("Add from Documents"),
            noCreate: true,
            multiSelect: true,
            resModel: "document.document",
            domain: [
                ["type", "=", "binary"],
                ["shortcut_document_id", "=", false],
                [
                    "file_extension",
                    "in",
                    ["pdf", "docx", "doc", "xlsx", "xls", "pptx", "ppt", "odt", "ods"],
                ],
            ],
            onSelected: async (resIds) => {
                if (resIds.length) {
                    this.addSelectedDocumentsToAgent(resIds);
                }
            },
        });
    },

    async addSelectedDocumentsToAgent(documentIds) {
        this.state.loading = true;
        await this.orm.call(
            "document.document",
            "create_ai_agent_sources_from_documents",
            [documentIds, this.agentId],
        );
        this.state.loading = false;
        return this.actionService.doAction({
            type: "ir.actions.client",
            tag: "soft_reload",
        });
    },
});
