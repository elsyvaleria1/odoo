/** @odoo-module native */
import { knowledgeContextOf } from "@knowledge/js/knowledge_context";
import { registerMessageAction } from "@mail/core/common/message_actions";
import { _t } from "@web/core/translation";

registerMessageAction("closeThread", {
    condition: ({ owner }) =>
        knowledgeContextOf(owner).closeThread &&
        !knowledgeContextOf(owner).isResolved(),
    icon: "fa-solid fa-check",
    name: _t("Mark the discussion as resolved"),
    onSelected: ({ owner }) => knowledgeContextOf(owner).closeThread(),
    sequence: 0,
});

registerMessageAction("openThread", {
    condition: ({ owner }) =>
        knowledgeContextOf(owner).openThread && knowledgeContextOf(owner).isResolved(),
    icon: "fa-solid fa-retweet",
    name: _t("Re-open the discussion"),
    onSelected: ({ owner }) => knowledgeContextOf(owner).openThread(),
    sequence: 0,
});
