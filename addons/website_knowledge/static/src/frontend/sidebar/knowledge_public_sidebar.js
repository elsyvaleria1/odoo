/** @odoo-module native */
import { ArticleSearchDialog } from "@knowledge/components/article_search_dialog/article_search_dialog";
import {
    provideKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import { Component, onMounted, onWillStart, proxy, t, useProps } from "@odoo/owl";
import { ResizablePanel } from "@web/components/resizable_panel";
import { router, routerBus } from "@web/core/browser/router";
import { rpc } from "@web/core/network";
import { Transition } from "@web/core/transition";
import { KeepLast } from "@web/core/utils/concurrency";
import {
    useBus,
    useChildRef,
    useForwardRefToParent,
    useMountedListener,
    useService,
} from "@web/core/utils/hooks";
import { useLayoutEffect } from "@web/core/utils/layout_effect";

class KnowledgePublicResizablePanel extends ResizablePanel {
    static props = { ...ResizablePanel.props, handleRef: t.function() };

    setup() {
        super.setup();
        useForwardRefToParent("handleRef", this.handleRefRef);
    }
}

class SidebarArticle {
    /**
     * @param {integer} id
     * @param {string} icon
     * @param {string} name
     */
    constructor(id, icon, name) {
        this.id = id;
        this.icon = icon;
        this.name = name;
        this.children = [];
        this.isUnfolded = false;
        this.childrenAreLoaded = false;
        this.parent = null;
    }

    async loadChildren() {
        const children = await rpc("/knowledge/public/children", {
            article_id: this.id,
        });
        this.children = children.map(
            (child) => new SidebarArticle(child.id, child.icon, child.name),
        );
        this.childrenAreLoaded = true;
    }

    async toggleFold() {
        if (!this.isUnfolded && !this.childrenAreLoaded) {
            await this.loadChildren();
        }
        this.isUnfolded = !this.isUnfolded;
    }
}

export class KnowledgePublicSidebar extends Component {
    static template = "website_knowledge.publicSidebar";
    static components = { ResizablePanel: KnowledgePublicResizablePanel, Transition };
    static props = {
        onMounted: t.function(),
        subEnv: t.object(),
        viewState: t.object(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        provideKnowledgeContext(this.props.subEnv);
        this.knowledgeContext = useKnowledgeContext();
        this.rootArticle = proxy(new SidebarArticle(null, null, null));
        this.articlesMap = new Map();
        this.record = proxy(this.knowledgeContext.record);
        this.dialog = useService("dialog");
        this.keepLastSidebarLoad = new KeepLast();
        onWillStart(() => {
            this.loadSidebar();
        });
        onMounted(() => {
            this.props.onMounted();
        });
        useLayoutEffect(
            () => {
                const article = this.articlesMap.get(this.record.resId);
                if (this.props.viewState.showSidebar && !article?.isUnfolded) {
                    this.loadSidebar();
                }
            },
            () => [this.record.resId, this.props.viewState.showSidebar],
        );
        useBus(routerBus, "ROUTE_CHANGE", () =>
            this.knowledgeContext.openArticle(router.current.resId),
        );
        this.handleRef = useChildRef();
        const mouseDownHandler = () => {
            this.handleRef.el.classList.add("o_knowledge_sidebar_active_handle");
        };
        useLayoutEffect(
            (el) => {
                if (el) {
                    el.addEventListener("mousedown", mouseDownHandler);
                    return () => el.removeEventListener("mousedown", mouseDownHandler);
                }
            },
            () => [this.handleRef.el],
        );
        useMountedListener(document, "mouseup", () => {
            this.handleRef.el?.classList.remove("o_knowledge_sidebar_active_handle");
        });
    }

    async loadSidebar() {
        const articles = await this.keepLastSidebarLoad.add(
            rpc("/knowledge/public/sidebar", {
                article_id: this.knowledgeContext.record.resId,
            }),
        );
        this.articlesMap = new Map();
        articles.forEach((article) => {
            this.articlesMap.set(
                article.id,
                new SidebarArticle(article.id, article.icon, article.name),
            );
        });
        articles.forEach((article) => {
            const currentArticle = this.articlesMap.get(article.id);
            const parent = this.articlesMap.get(article.parent_id);
            if (parent) {
                parent.children.push(currentArticle);
                currentArticle.parent = parent;
                if (!parent.isUnfolded) {
                    parent.isUnfolded = true;
                }
            } else {
                Object.assign(this.rootArticle, currentArticle);
            }
        });
        if (this.rootArticle.children.length) {
            this.rootArticle.isUnfolded = true;
        }
    }

    openSearchDialog() {
        this.dialog.add(ArticleSearchDialog, {
            search: (searchValue) =>
                rpc(`/knowledge/public/search`, {
                    search_value: searchValue,
                    subsite_root_id: this.rootArticle.id,
                }),
            select: (article) =>
                this.knowledgeContext
                    .openArticle(article.id)
                    .then(() => this.loadSidebar()),
        });
    }
}
