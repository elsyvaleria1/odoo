import {
    dragAndDropArticle,
    endKnowledgeTour,
    unfoldArticleFromSidebar,
} from "@knowledge/../tests/tours/knowledge_tour_utils";
import { registry } from "@web/core/registry";

registry
    .category("web_tour.tours")
    .add("knowledge_resequence_children_of_readonly_parent_tour", {
        steps: () => [
            unfoldArticleFromSidebar("Readonly Parent"),
            {
                trigger:
                    "li.o_article:has(li:nth-child(1):contains(Child 1)):has(li:nth-child(2):contains(Child 2))",
            },
            {
                trigger: ".o_article_active:contains(Readonly Parent)",
                run: function () {
                    const children =
                        this.anchor.parentElement.querySelectorAll(".o_article_name");
                    dragAndDropArticle(children[2], children[1]);
                },
            },
            {
                trigger:
                    "li.o_article:has(li:nth-child(1):contains(Child 2)):has(li:nth-child(2):contains(Child 1))",
            },
            {
                trigger: ".o_article_active:contains(Readonly Parent)",
                run: function () {
                    const child1 =
                        this.anchor.parentElement.querySelectorAll(
                            ".o_article_name",
                        )[2];
                    dragAndDropArticle(child1, this.anchor);
                },
            },
            {
                trigger:
                    ".o_section:contains(Workspace):has(li:nth-child(1):contains(Child 1)):has(li:nth-child(2):contains(Readonly Parent))",
            },
            ...endKnowledgeTour(),
        ],
    });
