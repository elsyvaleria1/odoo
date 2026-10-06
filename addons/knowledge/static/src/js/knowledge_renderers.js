/** @odoo-module native */
import { useKnowledgeContext } from "@knowledge/js/knowledge_context";
import { useListener } from "@odoo/owl";
import { FormRenderer } from "@web/views/form";

export class KnowledgeArticleFormRenderer extends FormRenderer {
    //--------------------------------------------------------------------------
    // Component
    //--------------------------------------------------------------------------
    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        useListener(document, "click", (event) => {
            if (event.target.classList.contains("o_nocontent_create_btn")) {
                this.knowledgeContext.createArticle("private");
            }
        });
    }
}
