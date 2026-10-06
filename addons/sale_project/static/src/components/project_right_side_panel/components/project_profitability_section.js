/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { formatFieldFloat, formatFloatTime } from "@web/core/formatters";
import { useService } from "@web/core/utils/hooks";

export class ProjectProfitabilitySection extends Component {
    static props = {
        revenue: t.object(),
        labels: t.object(),
        formatMonetary: t.function(),
        onProjectActionClick: t.function(),
        onClick: t.function(),
        projectId: t.number(),
        context: t.object(),
    };
    static template = "sale_project.ProjectProfitabilitySection";
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.state = proxy({
            isFolded: true,
            displayLoadMore: null,
            saleItems: [],
        });
    }

    get revenue() {
        return this.props.revenue;
    }

    async toggleSaleItems() {
        if (this.state.displayLoadMore === null) {
            await this.onLoadMoreClick();
        }
        this.state.isFolded = !this.state.isFolded;
    }

    formatValue(value, unit) {
        return unit === "Hours" ? formatFloatTime(value) : formatFieldFloat(value);
    }

    _getOrmValue(offset, section_id) {
        return {
            function: "get_sale_items_data",
            args: [this.props.projectId, offset, 5, true, section_id],
        };
    }

    async onLoadMoreClick() {
        const offset = this.state.saleItems.length;
        const orm_value = this._getOrmValue(offset, this.props.revenue.id);
        const newItems = await this.orm.call(
            "project.project",
            orm_value.function,
            orm_value.args,
            {
                context: this.props.context,
            },
        );
        this.state.saleItems.push(...newItems.sol_items);
        this.state.displayLoadMore = newItems.displayLoadMore;
    }

    async onSaleItemActionClick(params) {
        if (params.resId && params.type !== "object") {
            const action = await this.actionService.loadAction(
                params.name,
                this.props.context,
            );
            this.actionService.doAction({
                ...action,
                res_id: params.resId,
                views: [[false, "form"]],
            });
        } else {
            this.props.onProjectActionClick(params);
        }
    }
}
