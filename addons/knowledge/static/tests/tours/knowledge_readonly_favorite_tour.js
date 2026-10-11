import {
    dragAndDropArticle,
    endKnowledgeTour,
} from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("knowledge_readonly_favorite_tour", {
    steps: () => [
        {
            trigger: ".o_article_active:contains(Readonly Article 1)",
        },
        {
            trigger: ".o_knowledge_toggle_favorite:has(.fa-regular.fa-star)",
            run: "click",
        },
        {
            trigger: ".o_knowledge_toggle_favorite:has(.fa-solid.fa-star)",
        },
        {
            trigger: 'section[data-section="favorites"]:contains("Readonly Article 1")',
        },
        {
            trigger:
                '.o_knowledge_sidebar .o_article_name:contains("Readonly Article 2")',
            run: "click",
        },
        {
            trigger: ".o_article_active:contains(Readonly Article 2)",
        },
        {
            trigger: ".o_knowledge_toggle_favorite:has(.fa-regular.fa-star)",
            run: "click",
        },
        {
            trigger:
                'section[data-section="favorites"] li:last:contains("Readonly Article 2")',
            run: ({ queryOne }) =>
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="favorites"] li:last .o_article_handle',
                    ),
                    queryOne(
                        'section[data-section="favorites"] li:first .o_article_handle',
                    ),
                ),
        },
        {
            trigger:
                'section[data-section="favorites"] li:first:contains("Readonly Article 2")',
        },
        {
            trigger:
                'section[data-section="favorites"] li:last:contains("Readonly Article 1")',
        },
        ...endKnowledgeTour(),
    ],
});
