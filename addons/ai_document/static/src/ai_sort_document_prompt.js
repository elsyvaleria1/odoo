/** @odoo-module native */
import { aiPrompt } from "@ai/ai_prompt/ai_prompt_field";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";

class AiSortDocumentsPromptField extends aiPrompt.component {
    get missingRecordsMessage() {
        return _t("⚠️ Tell the AI where to sort your documents with /record.");
    }
}

registry.category("fields").add("ai_sort_documents_prompt", {
    ...aiPrompt,
    component: AiSortDocumentsPromptField,
});
