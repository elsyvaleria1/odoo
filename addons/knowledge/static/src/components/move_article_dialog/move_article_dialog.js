/** @odoo-module native */
import { Component, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { SelectMenu } from "@web/components/select_menu";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";
import { Dialog } from "@web/ui/dialog";

class MoveArticleDialog extends Component {
    static template = "knowledge.MoveArticleDialog";
    static components = { Dialog, SelectMenu };
    static props = { close: t.function(), knowledgeArticleRecord: t.object() };
    props = useProps(this.constructor.props);

    setup() {
        this.size = "md";
        this.orm = useService("orm");
        this.state = proxy({
            selectedParentArticle: false,
            selectionDisplayGroups: [],
        });
        this.placeholderLabel = _t("Choose an Article...");
        this.toggler = elementRef();

        onWillStart(() => this.fetchValues());

        useLayoutEffect(
            (toggler) => {
                toggler.click();
            },
            () => [this.toggler.el],
        );
    }

    /** @param {String} searchValue */
    async fetchValues(searchValue) {
        const knowledgeArticles = await this.orm.call(
            "knowledge.article",
            "get_valid_parent_options",
            [this.props.knowledgeArticleRecord.resId],
            { search_term: searchValue },
        );
        const formattedKnowledgeArticles = knowledgeArticles.map(
            ({ id, display_name, root_article_id }) => ({
                value: {
                    parentArticleId: id,
                    rootArticleName:
                        root_article_id[0] !== id ? root_article_id[1] : "",
                },
                label: display_name,
            }),
        );
        const selectionGroups = [
            {
                label: _t("Categories"),
                choices: [
                    {
                        value: { parentArticleId: "private" },
                        label: _t("Private"),
                    },
                    {
                        value: { parentArticleId: "workspace" },
                        label: _t("Workspace"),
                    },
                ],
            },
            {
                label: _t("Articles"),
                choices: formattedKnowledgeArticles,
            },
        ];
        if (this.props.knowledgeArticleRecord.data.category !== "private") {
            selectionGroups[0].choices.push({
                value: { parentArticleId: "shared" },
                label: _t("Shared"),
            });
        }
        this.state.selectionDisplayGroups = selectionGroups;
        this.state.choices = [
            ...selectionGroups[0].choices,
            ...formattedKnowledgeArticles,
        ];
    }

    selectArticle(value) {
        this.state.selectedParentArticle = this.state.choices.find(
            (knowledgeArticle) =>
                knowledgeArticle.value.parentArticleId === value.parentArticleId,
        );
    }

    async confirmArticleMove() {
        if (!this.state.selectedParentArticle) {
            return;
        }
        const selectedParentArticle =
            this.state.selectedParentArticle.value.parentArticleId;
        const params = {};
        if (typeof selectedParentArticle === "number") {
            params.parent_id = selectedParentArticle;
        } else {
            params.category = selectedParentArticle;
        }
        await this.orm.call(
            "knowledge.article",
            "move_to",
            [this.props.knowledgeArticleRecord.resId],
            params,
        );
        await this.props.knowledgeArticleRecord.model.load();
        this.props.close();
    }

    get loggedUserPicture() {
        return `/web/image?model=res.users&field=avatar_128&id=${user.userId}`;
    }

    get moveArticleLabel() {
        return _t(
            'Move "%s" under:',
            this.props.knowledgeArticleRecord.data.display_name,
        );
    }
}

export default MoveArticleDialog;
