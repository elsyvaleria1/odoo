/** @odoo-module native */
import { getEmbeddedProps } from "@html_editor/others/embedded_component_utils";
import { WithLazyLoading } from "@knowledge/components/with_lazy_loading/with_lazy_loading";
import {
    provideKnowledgeContext,
    useKnowledgeContext,
} from "@knowledge/js/knowledge_context";
import { EmbeddedView } from "@knowledge/views/embedded_view";
import {
    Component,
    onError,
    onWillStart,
    proxy,
    t,
    useListener,
    useProps,
} from "@odoo/owl";
import { CallbackRecorder } from "@web/core/action_hook";
import { makeContext } from "@web/core/context";
import { provideDebugContext } from "@web/core/debug/debug_context";
import { _t } from "@web/core/translation";
import {
    provideServices,
    useBus,
    useEventBus,
    useService,
    useServices,
} from "@web/core/utils/hooks";
import { provideViewConfig } from "@web/core/view_config_hooks";
import { getDefaultConfig } from "@web/views/view";

const VIEW_RECORDS_LIMITS = {
    kanban: 20,
    list: 40,
};

export class ReadonlyEmbeddedViewComponent extends Component {
    static components = {
        EmbeddedView,
        WithLazyLoading,
    };
    static props = { host: t.object(), viewProps: t.object() };
    static template = "knowledge.EmbeddedView";
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.bus = useEventBus();
        this.actionService = useService("action");
        this.notificationService = useService("notification");
        this.uiService = useService("ui");
        this.viewFilters = useService("knowledgeEmbedViewsFilters");
        provideDebugContext();
        this.state = proxy({
            error: false,
            isLoaded: false,
        });
        const services = useServices();
        const extendedServices = Object.create(services);
        extendedServices.action = Object.create(services.action);
        extendedServices.action.switchView = (viewType, props = {}) => {
            if (props.resId) {
                this.action.res_id = props.resId;
            }
            this.action.globalState = this.getEmbeddedViewGlobalState();
            this.actionService.doAction(this.action, { viewType });
        };

        this.config = { ...getDefaultConfig(), disableSearchBarAutofocus: true };
        provideViewConfig(this.config);
        provideKnowledgeContext({ isEmbeddedView: true, isEmbeddedReadonly: true });
        provideServices(extendedServices);
        this.knowledgeContext = useKnowledgeContext();

        useBus(this.bus, `KNOWLEDGE_EMBEDDED_${this.id}:OPEN`, () => {
            this.openView();
        });

        useListener(this.props.host, "focusin", () => {
            if (!this.props.host.contains(this.uiService.activeElement)) {
                this.uiService.activateElement(this.props.host);
            }
        });
        useListener(this.props.host, "focusout", (event) => {
            if (!this.props.host.contains(event.relatedTarget)) {
                this.uiService.deactivateElement(this.props.host);
            }
        });

        onWillStart(async () => {
            await this.loadEmbeddedView();
        });

        onError((error) => {
            console.error(error);
            this.state.error = true;
        });
    }

    get embeddedViewProps() {
        return {
            ...this.staticEmbeddedViewProps,
            additionalViewProps: { ...this.additionalViewProps },
            displayName: this.displayName,
            irFilters: this.irFilters,
        };
    }

    get additionalViewProps() {
        return this.props.viewProps.additionalViewProps;
    }

    get displayName() {
        return this.props.viewProps.displayName;
    }

    get favoriteFilters() {
        return this.props.viewProps.favoriteFilters;
    }

    get id() {
        return this.props.viewProps.id;
    }

    get irFilters() {
        return (Object.values(this.favoriteFilters || {}) || []).map((filter) => ({
            ...filter,
            context: JSON.stringify(filter.context),
        }));
    }

    async createRecord() {
        this.saveFilters();
        this.actionService.doAction({
            res_model: this.action.res_model,
            type: "ir.actions.act_window",
            views: [
                this.action.views.find(([, type]) => type === "form") || [
                    false,
                    "form",
                ],
            ],
        });
    }

    deleteFavoriteFilter() {
        this.notificationService.add(
            _t("You are not allowed to delete a favorite filter in this article."),
            {
                type: "danger",
            },
        );
    }

    /** @returns {Object} */
    getEmbeddedViewGlobalState() {
        const callbacks = this.__getGlobalState__.callbacks;
        let globalState;
        if (callbacks.length) {
            globalState = callbacks.reduce(
                (res, callback) => ({ ...res, ...callback() }),
                {},
            );
        }
        return { searchModel: globalState && globalState.searchModel };
    }

    async loadEmbeddedView() {
        this.__getGlobalState__ = new CallbackRecorder();
        const context = this.makeEmbeddedContext();
        this.action = await this.loadAction(context);
        this.config.views = this.action.views;
        this.config.setDisplayName(this.action.name);
        this.staticEmbeddedViewProps = this.prepareStaticEmbeddedViewProps(context);
        this.viewFilters.applyFilter(
            this.actionService.currentController,
            this.id,
            this.staticEmbeddedViewProps,
        );
        this.state.isLoaded = true;
    }

    async loadAction(context) {
        if (this.props.actWindow?.help) {
            delete this.props.actWindow.help;
        }
        const action = await this.actionService.loadAction(
            this.props.viewProps.actWindow || this.props.viewProps.actionXmlId,
            context,
        );
        if (action.type !== "ir.actions.act_window") {
            throw new Error(
                `Invalid action type "${action.type}". Expected "ir.actions.act_window"`,
            );
        }
        if (this.displayName) {
            action.name = this.displayName;
            action.display_name = this.displayName;
        }
        return action;
    }

    makeEmbeddedContext() {
        const context = makeContext([
            this.props.viewProps.context || {},
            {
                knowledgeEmbeddedViewId: this.id,
            },
        ]);
        return context;
    }

    openView() {
        this.saveFilters();
        const props = { ...this.additionalViewProps };
        if (this.action.context.orderBy) {
            try {
                props.orderBy = JSON.parse(this.action.context.orderBy);
            } catch {
                console.error("Parsing orderBy failed");
            }
        }
        if (this.displayName !== this.action.display_name) {
            this.action.display_name = this.displayName;
            this.action.name = this.displayName;
        }
        this.action.globalState = this.getEmbeddedViewGlobalState();
        this.actionService.doAction(this.action, {
            viewType: this.props.viewProps.viewType,
            props,
            additionalContext: {
                knowledgeEmbeddedViewId: this.id,
                isOpenedEmbeddedView: true,
            },
        });
    }

    prepareStaticEmbeddedViewProps(context) {
        return {
            context,
            createRecord: this.createRecord.bind(this),
            deleteEmbeddedViewFavoriteFilter: this.deleteFavoriteFilter.bind(this),
            domain: this.action.domain || [],
            __getGlobalState__: this.__getGlobalState__,
            globalState: { searchModel: context.knowledge_search_model_state },
            irFilters: this.irFilters,
            limit: VIEW_RECORDS_LIMITS[this.props.viewProps.type],
            loadActionMenus: true,
            loadIrFilters: true,
            noContentHelp: this.action.help,
            resModel: this.action.res_model,
            saveEmbeddedViewFavoriteFilter: this.saveFavoriteFilter.bind(this),
            searchViewId: this.action.searchViewId?.[0],
            selectRecord: this.selectRecord.bind(this),
            type: this.props.viewProps.viewType,
        };
    }

    saveFilters() {
        this.viewFilters.saveFilters(
            this.actionService.currentController,
            this.id,
            this.getEmbeddedViewGlobalState().searchModel,
        );
    }

    saveFavoriteFilter() {
        this.notificationService.add(
            _t("You are not allowed to save a favorite filter in this article."),
            {
                type: "danger",
            },
        );
    }

    selectRecord(resId) {
        this.saveFilters();
        if (this.action.res_model === "knowledge.article") {
            this.knowledgeContext.openArticle(resId);
        } else {
            this.actionService.doAction({
                res_id: resId,
                res_model: this.action.res_model,
                type: "ir.actions.act_window",
                views: [
                    this.action.views.find(([, type]) => type === "form") || [
                        false,
                        "form",
                    ],
                ],
            });
        }
    }
}

export const readonlyViewEmbedding = {
    name: "view",
    Component: ReadonlyEmbeddedViewComponent,
    getProps: (host) => ({ host, ...getEmbeddedProps(host) }),
};
