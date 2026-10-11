// @ts-check
/** @odoo-module native */

import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    toRaw,
    useProps,
} from "@odoo/owl";
import { getDefaultDomain } from "@web/components/domain_selector/utils";
import { DomainSelectorDialog } from "@web/components/domain_selector_dialog/domain_selector_dialog";
import {
    CallbackRecorder,
    provideActionCallbackRecorders,
    useActionCallbackRecorders,
    useSetupAction,
} from "@web/core/action_hook";
import { SEARCH_KEYS } from "@web/core/constants";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useLifecycleLog } from "@web/core/debug/logger_hooks";
import { SearchModelEvent } from "@web/core/events";
import { KeepLast, SupersededError } from "@web/core/utils/concurrency";
import { useBus, useService } from "@web/core/utils/hooks";
import { useViewConfig } from "@web/core/view_config_hooks";
import { provideWebContext } from "@web/core/web_context_hooks";
import { provideSearchModel, SearchModel } from "@web/search/search_model";
import { provideActiveView } from "@web/views/active_view";

const log = makeLogger("web.search.with_search");

export const withSearchProps = {
    slots: t.object(),
    SearchModel: t.function().optional(),
    resModel: t.string(),
    globalState: t.object().optional(),
    searchModelArgs: t.object().optional(),
    display: t.object().optional(),
    context: t.object().optional(),
    domain: t.array(t.or([t.string(), t.array()])).optional(),
    groupBy: t.array(t.string()).optional(),
    orderBy: t.array(t.object()).optional(),
    searchViewArch: t.string().optional(),
    searchViewIR: t.object().optional(),
    searchViewFields: t.object().optional(),
    searchViewId: t.or([t.number(), t.boolean()]).optional(),
    irFilters: t.array(t.object()).optional(),
    loadIrFilters: t.boolean().optional(),
    activateFavorite: t.boolean().optional(),
    dynamicFilters: t.array(t.object()).optional(),
    hideCustomGroupBy: t.boolean().optional(),
    searchMenuTypes: t.array(t.string()).optional(),
    canOrderByCount: t.boolean().optional(),
    defaultGroupBy: t.array(t.string()).optional(),
};

export class WithSearch extends Component {
    static template = "web.WithSearch";
    static props = withSearchProps;
    props = useProps(this.constructor.props);

    setup() {
        useLifecycleLog(log);
        const parentCallbacks = useActionCallbackRecorders();
        if (!parentCallbacks.__getContext__) {
            provideActionCallbackRecorders({ __getContext__: new CallbackRecorder() });
        }
        if (!parentCallbacks.__getOrderBy__) {
            provideActionCallbackRecorders({ __getOrderBy__: new CallbackRecorder() });
        }

        const SearchModelClass = this.props.SearchModel || SearchModel;
        this.searchModel = new SearchModelClass(
            SearchModelClass.useSearchScope(),
            {
                orm: useService("orm"),
                view: useService("view"),
                field: useService("field"),
                dialog: useService("dialog"),
                treeProcessor: useService("tree_processor"),
                DomainSelectorDialog,
                getDefaultDomain,
            },
            this.props.searchModelArgs,
        );

        const searchPanelState = this.props.globalState?.searchPanel
            ? JSON.parse(this.props.globalState?.searchPanel)
            : null;
        provideSearchModel(this.searchModel);
        provideActiveView(useViewConfig() ?? {}, this.searchModel);
        provideWebContext({ searchPanelState });

        this.state = proxy({ searchModelUpdates: 0 });
        useBus(
            this.searchModel,
            SearchModelEvent.UPDATE,
            () => this.state.searchModelUpdates++,
        );
        useSetupAction({
            getGlobalState: () => ({
                searchModel: JSON.stringify(this.searchModel.exportState()),
            }),
        });

        onWillStart(async () => {
            const config = Object.fromEntries(
                Object.entries(toRaw(this.props)).filter(
                    ([, value]) => value !== undefined,
                ),
            );
            if (config.globalState && config.globalState.searchModel) {
                config.state = JSON.parse(config.globalState.searchModel);
                delete config.globalState;
            }
            await log.measure("load", () => this.searchModel.load(config));
        });

        const reloadKeepLast = new KeepLast({ rejectSuperseded: true });

        onWillUpdateProps(async (nextProps) => {
            /** @type {Record<string, any>} */
            const config = {};
            for (const key of SEARCH_KEYS) {
                if (nextProps[key] !== undefined) {
                    config[key] = nextProps[key];
                }
            }
            try {
                await reloadKeepLast.add(
                    log.measure("reload", () => this.searchModel.reload(config)),
                );
            } catch (error) {
                if (!(error instanceof SupersededError)) {
                    throw error;
                }
                log.logic("reload-superseded", () => ({ keys: Object.keys(config) }));
            }
        });
    }

    get observedSearchModel() {
        void this.state.searchModelUpdates;
        return this.searchModel;
    }
}
