/** @odoo-module native */
import { ACCOUNTANT_KNOWLEDGE_PUBLIC_EMBEDDINGS } from "@accountant_knowledge/public/embedding_sets";
import {
    EmbeddedComponentInteraction,
    getEmbeddingMap,
} from "@html_editor/public/embedded_components/embedded_component_interaction";
import { patch } from "@web/core/utils/patch";

patch(EmbeddedComponentInteraction.prototype, {
    getEmbedding(name) {
        let embedding;
        if (this.knowledgePublicViewEl) {
            embedding = getEmbeddingMap(ACCOUNTANT_KNOWLEDGE_PUBLIC_EMBEDDINGS).get(
                name,
            );
        }
        return embedding ?? super.getEmbedding(name);
    },
});
