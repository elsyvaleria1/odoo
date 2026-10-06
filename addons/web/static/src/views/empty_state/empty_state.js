// @ts-check
/** @odoo-module native */

import {
    Component,
    onWillStart,
    onWillUpdateProps,
    proxy,
    t,
    useProps,
} from "@odoo/owl";
import { makeLogger } from "@web/core/debug/debug_logger";
import { useService } from "@web/core/utils/hooks";
import { useSearchModel } from "@web/search/search_model";

const log = makeLogger("web.empty_state");

export class EmptyState extends Component {
    static template = "web.EmptyState";
    static props = {
        noContentHelp: t.string().optional(),
        title: t.string().optional(),
        description: t.string().optional(),
        sample: t.boolean().optional(),
    };
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.searchModel = useSearchModel();
        this.state = proxy({ hiddenCount: 0 });
        /** @type {string | null} */
        this.countedFor = null;
        onWillStart(() => this.countHiddenRecords(this.props));
        onWillUpdateProps((nextProps) => this.countHiddenRecords(nextProps));
    }

    get isFiltered() {
        return this.state.hiddenCount > 0;
    }

    get showDefaultHelper() {
        return !this.props.noContentHelp;
    }

    /** @param {{ sample?: boolean }} props */
    async countHiddenRecords(props) {
        const searchModel = this.searchModel;
        const countedFor = `${searchModel?.domainString}|${Boolean(props.sample)}`;
        if (countedFor === this.countedFor) {
            return;
        }
        this.countedFor = countedFor;
        const filtering = searchModel?.facets.some(
            (/** @type {{ type?: string }} */ facet) => facet.type !== "groupBy",
        );
        log.logic("evaluate", () => ({
            resModel: searchModel?.resModel,
            filtering,
            sample: Boolean(props.sample),
        }));
        if (props.sample || !searchModel?.resModel || !filtering) {
            this.state.hiddenCount = 0;
            return;
        }
        const end = log.perf("countHidden");
        const hiddenCount = await this.orm.searchCount(
            searchModel.resModel,
            searchModel.globalDomain,
            { context: searchModel.globalContext },
        );
        end({ resModel: searchModel.resModel, hiddenCount });
        this.state.hiddenCount = hiddenCount;
    }

    clearSearch() {
        this.searchModel.clearQuery();
    }
}
