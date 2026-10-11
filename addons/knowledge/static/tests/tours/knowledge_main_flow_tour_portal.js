import { dragAndDropArticle } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

let workspaceArticleResId;
let privateArticleResId;

/**
 * Extract the resId from a Knowledge portal URL of scheme:
 * /knowledge/article/{resId}
 * @param {URL} url
 * @returns {Number} resId
 */
function extractURLResID(url) {
    return parseInt((url.pathname.match("/knowledge/article/([0-9]+)") || []).at(1));
}

registry.category("web_tour.tours").add("knowledge_main_flow_tour_portal", {
    url: "/knowledge/home",
    steps: () => [
        {
            trigger: ".o_section_create",
            run: (actionHelper) => {
                const url = new URL(browser.location);
                workspaceArticleResId = extractURLResID(url);
                if (!workspaceArticleResId) {
                    throw new Error(
                        `Expected pathname to be like /knowledge/article/{id}, got ${url.pathname} instead.`,
                    );
                }
                actionHelper.click();
            },
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("Untitled")',
            run: () => {
                const url = new URL(browser.location);
                const resId = extractURLResID(url);
                if (resId !== workspaceArticleResId + 1) {
                    throw new Error(
                        `Expected pathname to be like /knowledge/article/${workspaceArticleResId + 1}, got ${url.pathname} instead.`,
                    );
                }
            },
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit My Private Article && click body",
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: "editor Content of My Private Article",
        },
        {
            trigger: "body",
            run: () => {
                if (
                    document.querySelectorAll(
                        'section[data-section="workspace"] .o_article .o_article_name',
                    ).length !== 1
                ) {
                    throw new Error(
                        "Internal Workspace Article is not supposed to be visible for portal user.",
                    );
                }
            },
        },
        {
            trigger: ".o_knowledge_search",
            run: "click",
        },
        {
            trigger: ".o_article_search_dialog input",
            run: "edit Workspace Article",
        },
        {
            trigger: `.o_article_search_item:contains(Workspace Article)`,
            run: "click",
        },
        {
            trigger: '.o_knowledge_editor:contains("Content of Workspace Article")',
        },
        {
            trigger: ".note-editable.odoo-editor-editable",
            run: "editor Edited Content of Workspace Article",
        },
        {
            content: "Hover on Workspace Article to make create article visible",
            trigger: ".o_article:contains(Workspace Article)",
            run: "hover && click .o_article:contains(Workspace Article) a.o_article_create",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Child Article 1 && click body",
        },
        {
            content: "create child article (2)",
            trigger: ".o_article:contains(Workspace Article)",
            run: "hover && click .o_article:contains(Workspace Article) a.o_article_create",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Untitled")',
        },
        {
            trigger: ".o_hierarchy_article_name > input",
            run: "edit Child Article 2 && click body",
        },
        {
            trigger:
                'section[data-section="workspace"] .o_article .o_article_name:contains("Workspace Article")',
            run: "click",
        },
        {
            trigger:
                '.o_knowledge_editor:contains("Edited Content of Workspace Article")',
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger:
                'div.o_favorite_container .o_article .o_article_name:contains("Workspace Article")',
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("My Private Article")',
            run: "click",
        },
        {
            trigger: '.o_knowledge_editor:contains("My Private Article")',
            run: () => {
                privateArticleResId = extractURLResID(new URL(browser.location));
                if (privateArticleResId === workspaceArticleResId) {
                    throw new Error(
                        `Expected private article resId ${privateArticleResId} to be different from workspace article resId ${workspaceArticleResId}.`,
                    );
                }
                browser.history.back();
            },
        },
        {
            trigger:
                '.o_knowledge_editor:contains("Edited Content of Workspace Article")',
            run: () => {
                const resId = extractURLResID(new URL(browser.location));
                if (resId !== workspaceArticleResId) {
                    throw new Error(
                        `Expected to be back on the workspace article with resId ${workspaceArticleResId}, got ${resId} instead.`,
                    );
                }
                browser.history.forward();
            },
        },
        {
            trigger: '.o_knowledge_editor:contains("My Private Article")',
            run: () => {
                const resId = extractURLResID(new URL(browser.location));
                if (resId !== privateArticleResId) {
                    throw new Error(
                        `Expected to be back on the private article with resId ${privateArticleResId}, got ${resId} instead.`,
                    );
                }
            },
        },
        {
            trigger: ".o_knowledge_toggle_favorite",
            run: "click",
        },
        {
            trigger: ".o_knowledge_toggle_favorite .fa-star",
        },
        {
            trigger:
                'div.o_favorite_container .o_article_handle:contains("My Private Article")',
            run: ({ queryOne }) => {
                dragAndDropArticle(
                    queryOne(
                        'div.o_favorite_container .o_article_handle:contains("My Private Article")',
                    ),
                    queryOne(
                        'div.o_favorite_container .o_article_handle:contains("Workspace Article")',
                    ),
                );
            },
        },
        {
            trigger:
                'div.o_favorite_container ul li:first:contains("My Private Article")',
        },
    ],
});
