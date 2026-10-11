import { dragAndDropArticle } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

registry.category("web_tour.tours").add("knowledge_sidebar_readonly_tour", {
    url: "/odoo",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_tree .o_article:contains("Workspace Article") + .o_article:contains("Private Article")',
        },
        {
            trigger:
                '.o_article.readonly .o_article_handle:contains("Private Article") .o_article_icon',
            run: 'hover && click .o_article.readonly .o_article_handle:contains("Private Article") .o_article_caret .fa-caret-right',
        },
        {
            trigger: '.o_article:contains("Private Child")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="workspace"] .o_article_name:contains("Workspace Article")',
                    ),
                    queryOne(
                        'section[data-section="workspace"] .o_article_name:contains("Private Article")',
                    ),
                );
            },
        },
        {
            trigger: '.modal-title:contains("Move cancelled")',
        },
        {
            trigger: ".modal-footer .btn-primary",
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_tree .o_article:contains("Workspace Article") + .o_article:contains("Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'section[data-section="workspace"] .o_article_name:contains("Private Article")',
                    ),
                    queryOne(
                        'section[data-section="workspace"] .o_article_name:contains("Workspace Article")',
                    ),
                );
            },
        },
        {
            trigger:
                '.o_knowledge_tree .o_article:contains("Workspace Article") + .o_article:contains("Private Article")',
        },
        {
            trigger:
                '.o_article:contains("Private Article") .o_article_emoji:contains("📄")',
            run: "click",
        },
        {
            trigger: "body:not(:has(.o-EmojiPicker))",
        },
    ],
});
