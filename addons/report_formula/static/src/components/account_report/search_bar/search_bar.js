/** @odoo-module native */
import { Component, onMounted, proxy, t, useProps } from "@odoo/owl";
import { useAccountReportContext } from "@report_formula/components/account_report/account_report_context";
import { elementRef } from "@web/core/utils/element_ref";

export class AccountReportSearchBar extends Component {
    static template = "report_formula.AccountReportSearchBar";
    static props = { initialQuery: t.string().optional() };
    props = useProps(this.constructor.props);

    setup() {
        this.reportContext = useAccountReportContext();
        this.searchText = elementRef();
        this.controller = proxy(this.reportContext.controller);

        onMounted(() => {
            if (this.props.initialQuery) {
                this.searchText.el.value = this.props.initialQuery;
                this.search();
            }
        });
    }

    async search() {
        const inputText = this.searchText.el.value.trim();
        const query = inputText.toLowerCase();
        const linesIDsMatched = [];

        await this.controller.reportLoadingPromise;

        if (query.length) {
            for (const line of this.controller.lines) {
                if (!line.name) {
                    continue;
                }

                const lineName = line.name.trim().toLowerCase();
                const match = lineName.indexOf(query) !== -1;

                if (match) {
                    linesIDsMatched.push(line.id);
                }
            }
            this.controller.lines_searched = linesIDsMatched;
            this.controller.updateOption("filter_search_bar", inputText);
        } else {
            delete this.controller.lines_searched;
            this.controller.deleteOption("filter_search_bar");
        }
    }
}
