/** @odoo-module native */
import { ValuationChart } from "@equity/components/valuation_chart/valuation_chart";
import { useValuationChartActionSampleData } from "@equity/components/valuation_chart_action/valuation_chart_action_sample_data";
import { Component, markup, onWillStart, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { EmptyState } from "@web/views/empty_state/empty_state";
import { standardActionServiceProps } from "@web/webclient/actions";

export class ValuationChartAction extends Component {
    static template = "equity.ValuationChartAction";
    static props = { ...standardActionServiceProps };
    static components = { EmptyState, ValuationChart };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.isSample = false;
        this.sampleData = useValuationChartActionSampleData();

        onWillStart(async () => {
            this.chartData = await this.orm.call(
                "equity.valuation",
                "get_all_partners_valuation_chart_data",
                [],
            );
            if (this.chartData.labels.length === 0) {
                this.chartData = this.sampleData.getSampleData();
                this.isSample = true;
            }
        });
    }

    get noContentHelp() {
        const helpTitle = _t("No valuations yet!");
        const helpDescription = _t(
            "Add some valuations over the past year to see some data here.",
        );
        return markup`<p class="o_view_nocontent_smiling_face">${helpTitle}</p><p>${helpDescription}</p>`;
    }
}

registry.category("actions").add("equity.ValuationChart", ValuationChartAction);
