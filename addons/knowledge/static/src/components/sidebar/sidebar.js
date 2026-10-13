/** @odoo-module native */
import { ArticleSearchDialog } from "@knowledge/components/article_search_dialog/article_search_dialog";
import { ArticleTemplatePickerDialog } from "@knowledge/components/article_template_picker_dialog/article_template_picker_dialog";
import {
    provideChildKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import {
    Component,
    observe,
    onWillStart,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { localization } from "@web/core/l10n/localization";
import { _t } from "@web/core/translation";
import { user } from "@web/core/user";
import { useNestedSortable } from "@web/core/utils/dnd";
import { elementRef } from "@web/core/utils/element_ref";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { throttleForAnimation } from "@web/core/utils/timing";
import { useRecordObserver } from "@web/fields/hooks/record_observer";
import { provideViewModel } from "@web/model/model";
import { ConfirmationDialog } from "@web/ui/dialog";

import {
    KnowledgeSidebarFavoriteSection,
    KnowledgeSidebarPrivateSection,
    KnowledgeSidebarSharedSection,
    KnowledgeSidebarWorkspaceSection,
} from "./sidebar_section.js";

export const SORTABLE_TOLERANCE = 10;

export class KnowledgeSidebar extends Component {
    static props = { record: t.object() };
    static template = "knowledge.Sidebar";
    static components = {
        KnowledgeSidebarFavoriteSection,
        KnowledgeSidebarPrivateSection,
        KnowledgeSidebarSharedSection,
        KnowledgeSidebarWorkspaceSection,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.knowledgeContext = useKnowledgeContext();
        this.bus = useEventBus();
        this.command = useService("command");
        this.actionService = useService("action");
        this.dialog = useService("dialog");
        this.hotkey = useService("hotkey");
        this.orm = useService("orm");

        this.favoriteTree = elementRef();
        this.mainTree = elementRef();

        this.currentData = {};

        this.storageKeys = {
            size: "knowledge.sidebarSize",
            unfoldedArticles: "knowledge.unfolded.ids",
            unfoldedFavorites: "knowledge.unfolded.favorite.ids",
        };

        this.unfoldedArticlesIds = observe(
            new Set(
                localStorage
                    .getItem(this.storageKeys.unfoldedArticles)
                    ?.split(";")
                    .map(Number),
            ),
            () =>
                localStorage.setItem(
                    this.storageKeys.unfoldedArticles,
                    Array.from(this.unfoldedArticlesIds).join(";"),
                ),
        );
        this.unfoldedFavoritesIds = observe(
            new Set(
                localStorage
                    .getItem(this.storageKeys.unfoldedFavorites)
                    ?.split(";")
                    .map(Number),
            ),
            () =>
                localStorage.setItem(
                    this.storageKeys.unfoldedFavorites,
                    Array.from(this.unfoldedFavoritesIds).join(";"),
                ),
        );

        provideChildKnowledgeContext({
            fold: this.fold.bind(this),
            getArticle: this.getArticle.bind(this),
            unfold: this.unfold.bind(this),
        });
        provideViewModel(this.props.record.model);

        this.state = proxy({
            dragging: false,
            sidebarSize: localStorage.getItem(this.storageKeys.size) || 300,
            resizing: false,
        });

        this.loadArticles();

        useBus(this.bus, "KNOWLEDGE:RELOAD_SIDEBAR", async () => {
            await this.loadArticles();
        });

        useListener(
            browser,
            "keydown",
            (ev) => {
                if (this.isPortalUser && ev.key === "k" && (ev.ctrlKey || ev.metaKey)) {
                    ev.preventDefault();
                    ev.stopImmediatePropagation();
                    this.onSearchBarClick();
                }
            },
            { capture: true },
        );

        useNestedSortable({
            ref: this.favoriteTree,
            edgeScrolling: {
                speed: 10,
                threshold: 15,
            },
            preventDrag: (el) =>
                !el.parentElement.classList.contains("o_tree") &&
                el.classList.contains("readonly"),
            tolerance: SORTABLE_TOLERANCE,
            onDrop: ({ element, next, parent }) => {
                if (!parent) {
                    const articleId = parseInt(element.dataset.articleId);
                    const beforeId = next ? parseInt(next.dataset.articleId) : false;
                    this.resequenceFavorites(articleId, beforeId);
                } else {
                    const article = this.getArticle(
                        parseInt(element.dataset.articleId),
                    );
                    const parentId = parseInt(parent.dataset.articleId);
                    const currentPosition = {
                        category: article.category,
                        parentId: article.parent_id,
                        beforeArticleId:
                            parseInt(element.nextElementSibling?.dataset.articleId) ||
                            false,
                    };
                    const newPosition = {
                        category: article.category,
                        parentId: parentId,
                        beforeArticleId: parseInt(next?.dataset.articleId) || false,
                    };
                    this.moveArticle(article, currentPosition, newPosition);
                }
            },
        });

        useNestedSortable({
            ref: this.mainTree,
            elements: "li.o_article",
            groups: () =>
                this.isInternalUser
                    ? ".o_section"
                    : ".o_section[data-section='private']",
            connectGroups: () => this.isInternalUser,
            nest: true,
            preventDrag: (el) => el.classList.contains("readonly"),
            tolerance: SORTABLE_TOLERANCE,
            onDragStart: () => (this.state.dragging = true),
            onDragEnd: () => (this.state.dragging = false),
            /**
             * @param {DOMElement} element
             * @param {DOMElement} next
             * @param {DOMElement} newGroup
             * @param {DOMElement} parent
             * @param {DOMElement} placeholder
             */
            onDrop: async ({ element, next, newGroup, parent, placeholder }) => {
                const article = this.getArticle(parseInt(element.dataset.articleId));
                if (newGroup.classList.contains("o_knowledge_sidebar_trash")) {
                    this.moveToTrash(article);
                    return;
                }
                const parentId = parent ? parseInt(parent.dataset.articleId) : false;
                if (placeholder.classList.contains("bg-danger")) {
                    this.rejectDrop(article, parentId);
                    return;
                }
                const currentPosition = {
                    category: article.category,
                    parentId: article.parent_id,
                    beforeArticleId:
                        parseInt(element.nextElementSibling?.dataset.articleId) ||
                        false,
                };
                const newPosition = {
                    category: newGroup.dataset.section,
                    parentId: parentId,
                    beforeArticleId: parseInt(next?.dataset.articleId) || false,
                };
                this.moveArticle(article, currentPosition, newPosition);
            },
            /**
             * @param {DOMElement} element
             * @param {DOMElement} parent
             * @param {DOMElement} newGroup
             * @param {DOMElement} placeholder
             */
            onMove: ({ element, parent, newGroup, placeholder }) => {
                if (parent) {
                    const currentParentId =
                        element.parentElement.parentElement.dataset.articleId;
                    const targetParentId = parent.dataset.articleId;
                    if (
                        currentParentId !== targetParentId &&
                        parent.classList.contains("readonly")
                    ) {
                        placeholder.classList.add("bg-danger");
                        return;
                    }
                } else if (newGroup.dataset.section === "shared") {
                    const article = this.getArticle(
                        parseInt(element.dataset.articleId),
                    );
                    if (article.category === "private") {
                        placeholder.classList.add("bg-danger");
                        return;
                    }
                }
                placeholder.classList.remove("bg-danger");
            },
        });

        onWillStart(async () => {
            this.isInternalUser = await user.hasGroup("base.group_user");
            this.isPortalUser = await user.hasGroup("base.group_portal");
            this.canCreateArticle = await user.checkAccessRight(
                "knowledge.article",
                "create",
            );
        });

        useRecordObserver(async (record) => {
            const nextDataParentId = record.data.parent_id
                ? record.data.parent_id.id
                : false;
            const article = this.getArticle(record.resId) || {
                id: record.resId,
                name: record.data.name,
                icon: record.data.icon,
                category: record.data.category,
                parent_id: nextDataParentId,
                is_locked: record.data.is_locked,
                user_can_write: record.data.user_can_write,
                is_article_item: record.data.is_article_item,
                is_user_favorite: record.data.is_user_favorite,
                child_ids: [],
            };
            if (this.state.articles[record.resId]) {
                if (record.data.is_article_item !== article.is_article_item) {
                    if (record.data.is_article_item) {
                        this.removeArticle(article);
                    } else {
                        this.insertArticle(article, {
                            parentId: article.parent_id,
                        });
                        this.showArticle(article);
                    }
                }
                if (record.data.is_user_favorite !== article.is_user_favorite) {
                    if (record.data.is_user_favorite) {
                        this.state.favoriteIds.push(article.id);
                    } else {
                        this.state.favoriteIds.splice(
                            this.state.favoriteIds.indexOf(article.id),
                            1,
                        );
                    }
                }
                if (
                    (nextDataParentId !== article.parent_id ||
                        record.data.category !== article.category) &&
                    (record.data.parent_id !== this.currentData.parent_id ||
                        record.data.category !== this.currentData.category)
                ) {
                    if (!this.getArticle(nextDataParentId)) {
                        await this.loadArticles();
                        this.showArticle(this.getArticle(record.resId));
                    } else {
                        this.repositionArticle(article, {
                            parentId: nextDataParentId,
                            category: record.data.category,
                        });
                    }
                }
                Object.assign(article, {
                    name: record.data.name,
                    icon: record.data.icon,
                    is_locked: record.data.is_locked,
                    user_can_write: record.data.user_can_write,
                    is_article_item: record.data.is_article_item,
                    is_user_favorite: record.data.is_user_favorite,
                });
            } else if (!this.state.loading) {
                if (record.data.is_user_favorite) {
                    this.state.favoriteIds.push(record.resId);
                }
                this.state.articles[article.id] = article;
                if (!record.data.is_article_item) {
                    await this.insertArticle(article, {
                        category: article.category,
                        parentId: article.parent_id,
                    });
                    this.showArticle(article);
                    if (
                        nextDataParentId &&
                        this.getArticle(nextDataParentId)?.is_user_favorite
                    ) {
                        this.unfold(nextDataParentId, true);
                    }
                }
            }

            this.currentData = {
                parent_id: record.data.parent_id,
                category: record.data.category,
            };
        });
        this.bus.addEventListener(
            "knowledge.sidebar.insertNewArticle",
            async ({ detail }) => {
                if (this.getArticle(detail.articleId)) {
                    return;
                }
                const parent = detail.parentId
                    ? this.getArticle(detail.parentId)
                    : false;
                const newArticle = {
                    id: detail.articleId,
                    name: detail.name,
                    icon: detail.icon,
                    parent_id: parent ? parent.id : false,
                    category: parent ? parent.category : false,
                    is_locked: false,
                    user_can_write: true,
                    is_article_item: false,
                    is_user_favorite: false,
                    child_ids: [],
                };
                this.state.articles[newArticle.id] = newArticle;
                await this.insertArticle(newArticle, {
                    parentId: newArticle.parent_id,
                    category: parent ? parent.category : false,
                });
            },
        );
    }

    async browseTemplates() {
        if (await this.props.record.isDirty()) {
            await this.props.record.save();
        }
        const { articles, templates } = await this.orm.call(
            "knowledge.article",
            "get_available_templates",
        );
        this.dialog.add(ArticleTemplatePickerDialog, {
            articles: articles,
            templates: templates,
            /** @param {integer} articleId */
            onLoadArticle: async (articleId) => {
                const newArticleIds = await this.orm.call(
                    "knowledge.article",
                    "action_make_private_copy",
                    [articleId],
                    { preserve_name: true },
                );
                await this.actionService.doAction(
                    "knowledge.ir_actions_server_knowledge_home_page",
                    {
                        stackPosition: "replaceCurrentAction",
                        additionalContext: {
                            res_id: newArticleIds[0],
                        },
                    },
                );
            },
            /** @param {integer} templateId */
            onLoadTemplate: async (templateId) => {
                const [newArticleId] = await this.orm.call(
                    "knowledge.article",
                    "create_article_from_template",
                    [templateId],
                );
                await this.actionService.doAction(
                    "knowledge.ir_actions_server_knowledge_home_page",
                    {
                        stackPosition: "replaceCurrentAction",
                        additionalContext: {
                            res_id: newArticleId,
                        },
                    },
                );
            },
            /** @param {integer} articleId */
            onDeleteArticle: async (articleId) => {
                if (this.props.record.resId === articleId) {
                    await this.props.record.save();
                }
                await this.orm.write("knowledge.article", [articleId], {
                    is_listed_in_templates_gallery: false,
                });
                if (this.props.record.resId === articleId) {
                    this.props.record.load();
                }
            },
            /** @param {integer} templateId */
            onDeleteTemplate: async (templateId) => {
                await this.orm.unlink("knowledge.article", [templateId]);
            },
        });
    }

    /**
     * @param {Object} article
     * @param {String} category
     */
    async changeCategory(article, category) {
        article.category = category;
        if (article.id === this.props.record.id) {
            if (await this.props.record.isDirty()) {
                await this.props.record.save();
            } else {
                await this.props.record.model.load();
            }
        }
        for (const childId of article.child_ids) {
            this.changeCategory(this.getArticle(childId), category);
        }
    }

    /**
     * @param {String} -
     * @param {integer} -
     */
    createArticle(category, targetParentId) {
        try {
            this.knowledgeContext.createArticle(category, targetParentId);
        } catch {
            this.loadArticles();
        }
    }

    /**
     * @param {integer} articleId:
     * @param {boolean} isFavorite:
     */
    fold(articleId, isFavorite) {
        if (isFavorite) {
            this.unfoldedFavoritesIds.delete(articleId);
        } else {
            this.unfoldedArticlesIds.delete(articleId);
        }
    }

    /**
     * @param {integer} articleId
     * @returns {Object}
     */
    getArticle(articleId) {
        return this.state.articles[articleId];
    }

    /**
     * @param {String} category
     * @returns {Array}
     */
    getCategoryIds(category) {
        return this.state[`${category}Ids`];
    }

    /**
     * @param {Object} article
     * @param {Object} position
     * @param {integer} position.beforeArticleId
     * @param {String} position.category
     * @param {integer} position.parentId
     */
    async insertArticle(article, position) {
        if (position.parentId) {
            const parent = this.getArticle(position.parentId);
            if (parent) {
                if (!this.unfoldedArticlesIds.has(parent.id)) {
                    await this.unfold(parent.id, false);
                    if (parent.child_ids.includes(article.id)) {
                        return;
                    }
                }
                if (position.beforeArticleId) {
                    parent.child_ids.splice(
                        parent.child_ids.indexOf(position.beforeArticleId),
                        0,
                        article.id,
                    );
                } else {
                    parent.child_ids.push(article.id);
                }
                parent.has_article_children = true;
            }
        } else {
            const categoryIds = this.getCategoryIds(position.category);
            if (categoryIds) {
                if (position.beforeArticleId) {
                    categoryIds.splice(
                        categoryIds.indexOf(position.beforeArticleId),
                        0,
                        article.id,
                    );
                } else {
                    categoryIds.push(article.id);
                }
            }
        }
    }

    /**
     * @param {integer} articleId
     * @returns {Boolean}
     */
    isAncestor(articleId) {
        let article = this.getArticle(this.props.record.resId);
        while (article) {
            if (article.id === articleId) {
                return true;
            }
            article = this.getArticle(article.parent_id);
        }
        return false;
    }

    async loadArticles() {
        this.state.loading = true;
        Object.assign(this.state, {
            articles: {},
            favoriteIds: [],
            workspaceIds: [],
            sharedIds: [],
            privateIds: [],
        });
        const res = await this.orm.call(
            this.props.record.resModel,
            "get_sidebar_articles",
            [this.props.record.resId],
            {
                unfolded_ids: [
                    ...this.unfoldedArticlesIds,
                    ...this.unfoldedFavoritesIds,
                ],
            },
        );
        const children = {};
        for (const article of res.articles) {
            this.state.articles[article.id] = {
                ...article,
                child_ids: children[article.id] ? children[article.id] : [],
            };
            if (!article.is_article_item) {
                if (article.parent_id) {
                    const parent = this.getArticle(article.parent_id);
                    if (parent) {
                        parent.child_ids.push(article.id);
                    } else {
                        if (children[article.parent_id]) {
                            children[article.parent_id].push(article.id);
                        } else {
                            children[article.parent_id] = [article.id];
                        }
                    }
                } else {
                    this.getCategoryIds(article.category).push(article.id);
                }
            }
        }
        const ancestorRootArticleId = res.active_article_accessible_root_id;
        if (ancestorRootArticleId) {
            this.getCategoryIds(this.getArticle(ancestorRootArticleId).category).push(
                ancestorRootArticleId,
            );
        }
        this.state.favoriteIds = res.favorite_ids;
        this.showArticle(this.getArticle(this.props.record.resId));
        this.state.loading = false;
        this.resetUnfoldedArticles();
    }

    /** @param {object} article */
    async loadChildren(article) {
        const children = await this.orm.searchRead(
            this.props.record.resModel,
            [
                ["parent_id", "=", article.id],
                ["is_article_item", "=", false],
            ],
            ["name", "icon", "is_locked", "user_can_write", "has_article_children"],
            {
                load: "None",
                order: "sequence, id",
            },
        );
        for (const child of children) {
            article.child_ids.push(child.id);
            if (this.getArticle(child.id)) {
                continue;
            }
            this.state.articles[child.id] = {
                ...child,
                parent_id: article.id,
                child_ids: [],
                category: article.category,
                is_article_item: false,
                is_user_favorite: false,
            };
        }
    }

    /**
     * @param {Object} article
     * @param {Object} currentPosition
     * @param {integer} position.beforeArticleId
     * @param {String} position.category
     * @param {integer} position.parentId
     * @param {Object} newPosition
     * @param {integer} newPosition.beforeArticleId
     * @param {String} newPosition.category
     * @param {integer} newPosition.parentId
     */
    async moveArticle(article, currentPosition, newPosition) {
        const confirmMove = async (article, position) => {
            if (await this.props.record.isDirty()) {
                await this.props.record.save();
            }
            try {
                await this.orm.call(
                    this.props.record.resModel,
                    "move_to",
                    [article.id],
                    {
                        category: position.category,
                        parent_id: position.parentId,
                        before_article_id: position.beforeArticleId,
                    },
                );
            } catch (error) {
                this.loadArticles();
                throw error;
            }
            await this.props.record.load();
        };

        this.repositionArticle(article, newPosition);
        if (currentPosition.category === newPosition.category) {
            confirmMove(article, newPosition);
        } else {
            const emoji = article.icon || "";
            const name = article.name;
            let message;
            let confirmLabel;
            if (newPosition.category === "workspace") {
                message = _t(
                    'Are you sure you want to move "%(icon)s%(title)s" to the Workspace? It will be shared with all internal users.',
                    { icon: emoji, title: name || _t("Untitled") },
                );
                confirmLabel = _t("Move to Workspace");
            } else if (newPosition.category === "private") {
                message = _t(
                    'Are you sure you want to move "%(icon)s%(title)s" to private? Only you will be able to access it.',
                    { icon: emoji, title: name || _t("Untitled") },
                );
                confirmLabel = _t("Move to Private");
            } else if (newPosition.category === "shared") {
                if (newPosition.parentId) {
                    const parent = this.getArticle(newPosition.parentId);
                    message = _t(
                        'Are you sure you want to move "%(icon)s%(title)s" under "%(parentIcon)s%(parentTitle)s"? It will be shared with the same persons.',
                        {
                            icon: emoji,
                            title: name || _t("Untitled"),
                            parentIcon: parent.icon || "",
                            parentTitle: parent.name || _t("Untitled"),
                        },
                    );
                } else {
                    message = _t(
                        'Are you sure you want to move "%(icon)s%(title)s" to the Shared section? It will be shared with all listed members.',
                        { icon: emoji, title: name || _t("Untitled") },
                    );
                }
                confirmLabel = _t("Move to Shared");
            }
            this.dialog.add(ConfirmationDialog, {
                body: message,
                confirmLabel: confirmLabel,
                confirm: () => confirmMove(article, newPosition),
                cancel: () => {
                    this.repositionArticle(article, currentPosition);
                },
            });
        }
    }

    /** @param {Object} article */
    async moveToTrash(article) {
        try {
            await this.orm.call("knowledge.article", "action_send_to_trash", [
                article.id,
            ]);
        } catch {
            await this.loadArticles();
            return;
        }
        if (this.isAncestor(article.id)) {
            this.actionService.doAction(
                await this.orm.call("knowledge.article", "action_home_page", [false]),
                { stackPosition: "replaceCurrentAction" },
            );
        } else {
            this.removeArticle(article);
            this.removeFavorite(article);
        }
    }

    onSearchBarClick() {
        this.dialog.closeAll();
        if (this.isInternalUser) {
            this.command.openMainPalette({ searchValue: "?" });
        } else {
            this.dialog.add(ArticleSearchDialog, {
                search: (searchValue) => {
                    const params = { search_query: searchValue };
                    let searchFunction = "get_user_sorted_articles";
                    if (searchValue) {
                        searchFunction = "get_sorted_articles";
                        params.domain = this.searchDomain;
                    }
                    return this.orm.call(
                        "knowledge.article",
                        searchFunction,
                        [[]],
                        params,
                    );
                },
                select: (article) => this.knowledgeContext.openArticle(article.id),
            });
        }
    }

    get searchDomain() {
        return [
            "|",
            ["is_article_visible", "=", true],
            ["is_user_favorite", "=", true],
        ];
    }

    /**
     * @param {article}
     * @param {parentId}
     */
    rejectDrop(article, parentId) {
        let message;
        if (parentId) {
            const parent = this.getArticle(parentId);
            message = _t(
                'Could not move "%(icon)s%(title)s" under "%(parentIcon)s%(parentTitle)s", because you do not have write permission on the latter.',
                {
                    icon: article.icon || "",
                    title: article.name,
                    parentIcon: parent.icon || "",
                    parentTitle: parent.name,
                },
            );
        } else {
            message = _t("You need at least 2 members for the Article to be shared.");
        }
        this.dialog.add(ConfirmationDialog, {
            confirmLabel: _t("Close"),
            title: _t("Move cancelled"),
            body: message,
        });
    }

    /** @param {Object} article */
    removeArticle(article) {
        if (article.parent_id) {
            const parent = this.getArticle(article.parent_id);
            if (parent) {
                const articleIdx = parent.child_ids.indexOf(article.id);
                if (articleIdx !== -1) {
                    parent.child_ids.splice(parent.child_ids.indexOf(article.id), 1);
                    if (!parent.child_ids.length) {
                        this.fold(parent.id);
                        this.fold(parent.id, true);
                        parent.has_article_children = false;
                    }
                }
            }
        } else {
            const categoryIds = this.getCategoryIds(article.category);
            const articleIdx = categoryIds.indexOf(article.id);
            if (articleIdx !== -1) {
                categoryIds.splice(articleIdx, 1);
            }
        }
    }

    /** @param {Object} article */
    removeFavorite(article) {
        const favoriteIdx = this.state.favoriteIds.indexOf(article.id);
        if (favoriteIdx !== -1) {
            this.state.favoriteIds.splice(favoriteIdx, 1);
        }
    }

    /**
     * @param {Object} article
     * @param {Object} position
     * @param {integer} position.beforeArticleId
     * @param {String} position.category
     * @param {integer} position.parentId
     */
    async repositionArticle(article, position) {
        this.removeArticle(article);
        await this.insertArticle(article, position);
        if (article.parent_id !== position.parentId) {
            article.parent_id = position.parentId;
        }
        if (article.category !== position.category) {
            this.changeCategory(article, position.category);
        }
        this.showArticle(article);
    }

    /**
     * @param {integer} articleId
     * @param {integer} beforeId
     */
    resequenceFavorites(articleId, beforeId) {
        this.state.favoriteIds.splice(this.state.favoriteIds.indexOf(articleId), 1);
        if (beforeId) {
            this.state.favoriteIds.splice(
                this.state.favoriteIds.indexOf(beforeId),
                0,
                articleId,
            );
        } else {
            this.state.favoriteIds.push(articleId);
        }
        this.orm.call("knowledge.article.favorite", "resequence_favorites", [false], {
            article_ids: this.state.favoriteIds,
        });
    }

    resetUnfoldedArticles() {
        this.unfoldedArticlesIds.forEach((id) => {
            if (!this.getArticle(id)) {
                this.unfoldedArticlesIds.delete(id);
            }
        });
        this.unfoldedFavoritesIds.forEach((id) => {
            if (!this.getArticle(id)) {
                this.unfoldedFavoritesIds.delete(id);
            }
        });
    }

    resize() {
        const isRtl = localization.direction === "rtl";
        const onPointerMove = throttleForAnimation((event) => {
            event.preventDefault();
            this.state.sidebarSize = isRtl
                ? document.documentElement.clientWidth - event.pageX
                : event.pageX;
            browser.dispatchEvent(new Event("resize"));
        });
        const onPointerUp = () => {
            document.removeEventListener("pointermove", onPointerMove);
            this.state.resizing = false;
            document.body.style.cursor = "auto";
            document.body.style.userSelect = "auto";
            localStorage.setItem(this.storageKeys.size, this.state.sidebarSize);
            browser.dispatchEvent(new Event("resize"));
        };
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
        this.state.resizing = true;
        document.addEventListener("pointermove", onPointerMove);
        document.addEventListener("pointerup", onPointerUp, { once: true });
    }

    /** @param {object} article */
    showArticle(article) {
        while (
            article &&
            article.parent_id &&
            article.parent_id in this.state.articles
        ) {
            this.unfold(article.parent_id, false);
            article = this.getArticle(article.parent_id);
        }
    }

    /**
     * @param {integer} articleId:
     * @param {boolean} isFavorite:
     */
    async unfold(articleId, isFavorite) {
        const article = this.getArticle(articleId);
        if (article.has_article_children && !article.child_ids.length) {
            await this.loadChildren(article);
        }
        if (isFavorite) {
            this.unfoldedFavoritesIds.add(articleId);
        } else {
            this.unfoldedArticlesIds.add(articleId);
        }
    }
}
