import { htmlEditorVersions } from "@html_editor/html_migrations/html_migrations_utils";
import { endKnowledgeTour } from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";
import { stepUtils } from "@web_tour/tour_utils";

const VERSIONS = htmlEditorVersions();
const CURRENT_VERSION = VERSIONS.at(-1);

const testArticleName = "Test history Article";
function changeArticleContentAndSave(newContent) {
    return [
        {
            trigger: ".note-editable.odoo-editor-editable h1",
            run: `editor ${newContent}`,
        },
        {
            trigger: 'a[data-menu-xmlid="knowledge.knowledge_menu_home"]',
            run: "click",
        },
        {
            trigger:
                '.o_article:contains("' + testArticleName + '"):not(.o_article_active)',
            run: async () => {
                await new Promise((r) => setTimeout(r, 300));
            },
        },
        {
            trigger: '.o_article:contains("' + testArticleName + '") a.o_article_name',
            run: "click",
        },
        {
            trigger: '.o_article_active:contains("' + testArticleName + '") ',
        },
    ];
}

registry.category("web_tour.tours").add("knowledge_history_tour", {
    url: "/odoo?debug=1,tests",
    steps: () => [
        stepUtils.showAppsMenuItem(),
        {
            trigger: '.o_app[data-menu-xmlid="knowledge.knowledge_menu_root"]',
            run: "click",
        },
        {
            trigger: ".o_knowledge_create_article",
            run: "click",
        },
        {
            trigger:
                'section[data-section="private"] .o_article .o_article_name:contains("Untitled")',
        },
        ...changeArticleContentAndSave(testArticleName),
        ...changeArticleContentAndSave("Modified Title 01"),
        ...changeArticleContentAndSave("Modified Title 02"),
        ...changeArticleContentAndSave("Modified Title 03"),
        {
            trigger: ".o_knowledge_header .dropdown-toggle",
            run: "click",
        },
        {
            trigger: '.dropdown-item:contains("Open Version History")',
            run: "click",
        },
        {
            trigger: '.modal-header:contains("History")',
            run: "click",
        },
        {
            trigger: ".modal .html-history-dialog.html-history-loaded",
        },
        {
            trigger: ".html-history-dialog .revision-list .btn",
            run: function () {
                const items = document.querySelectorAll(".revision-list .btn");
                if (items.length !== 5) {
                    throw new Error(
                        "Expect 5 Revisions in the history dialog, got " + items.length,
                    );
                }
            },
        },
        {
            trigger:
                '.history-container .history-content-view:contains("Modified Title 03")',
            run: "click",
        },
        {
            trigger: ".html-history-dialog .revision-list .btn:nth-child(4)",
            run: "click",
        },
        {
            trigger: ".modal .html-history-dialog.html-history-loaded",
        },
        {
            trigger:
                '.history-container .history-content-view:contains("' +
                testArticleName +
                '")',
            run: "click",
        },
        {
            trigger: ".history-container .history-view-top-bar a:contains(Comparison)",
            run: "click",
        },
        {
            trigger: ".history-container .history-comparison-view",
            run: function () {
                const comparisonHtml = document
                    .querySelector(
                        ".history-container .history-comparison-unified .o_readonly",
                    )
                    .innerHTML.replace(/ data-heading-link-id="[0-9a-fA-F]+"/, "");
                const correctHtml =
                    `<h1 class="oe-hint" data-oe-version="${CURRENT_VERSION}"><added>Modified Title 03</added><removed>` +
                    testArticleName +
                    "</removed></h1>";
                if (comparisonHtml !== correctHtml) {
                    throw new Error(
                        "Expect comparison to be " +
                            correctHtml +
                            ", got " +
                            comparisonHtml,
                    );
                }
            },
        },
        {
            trigger: ".history-container .history-view-top-bar label:contains(Split)",
            run: "click",
        },
        {
            trigger: ".history-container .history-comparison-view",
            run: function () {
                const deletedElements = document.querySelectorAll(
                    ".history-container .history-comparison-split del",
                );
                const addedElements = document.querySelectorAll(
                    ".history-container .history-comparison-split ins",
                );

                if (deletedElements.length !== 3) {
                    throw new Error(
                        "Expect 3 deletedElement in the splitted comparison, got " +
                            deletedElements.length,
                    );
                }
                if (addedElements.length !== 3) {
                    throw new Error(
                        "Expect 3 deletedElement in the splitted comparison, got " +
                            addedElements.length,
                    );
                }
                if (
                    deletedElements[0].parentElement.textContent !==
                    "  Test history Article"
                ) {
                    throw new Error(
                        'Expect deleted string to be "Test history Article", got ' +
                            deletedElements[0].parentElement.textContent,
                    );
                }
                if (
                    addedElements[0].parentElement.textContent !== "  Modified Title 03"
                ) {
                    throw new Error(
                        'Expect added string to be "Modified Title 03", got ' +
                            addedElements[0].parentElement.textContent,
                    );
                }
            },
        },
        {
            trigger: ".modal-footer .btn-primary:enabled",
            run: "click",
        },
        {
            trigger:
                '.note-editable.odoo-editor-editable h1:contains("' +
                testArticleName +
                '")',
            run: "click",
        },
        ...endKnowledgeTour(),
    ],
});
