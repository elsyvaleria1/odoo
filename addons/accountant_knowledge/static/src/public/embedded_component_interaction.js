/** @odoo-module native */
import { ACCOUNTANT_KNOWLEDGE_PUBLIC_EMBEDDINGS } from "@accountant_knowledge/public/embedding_sets";
import {
    EmbeddedComponentInteraction,
    getEmbeddingMap,
} from "@html_editor/public/embedded_components/embedded_component_interaction";
import { patch } from "@web/core/utils/patch";

// Belongs in an accountant_website_knowledge module: it relies on
// `knowledgePublicViewEl`, which only website_knowledge sets. Kept here because
// it no-ops when that property is unset and no such module exists yet.
patch(EmbeddedComponentInteraction.prototype, {
    getEmbedding(name) {
        let embedding;
        if (this.knowledgePublicViewEl) {
            // Restrict Knowledge embedded components in the Knowledge public view.
            embedding = getEmbeddingMap(ACCOUNTANT_KNOWLEDGE_PUBLIC_EMBEDDINGS).get(
                name,
            );
        }
        return embedding ?? super.getEmbedding(name);
    },
});
