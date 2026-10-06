/** @odoo-module native */
import { EsgCarbonAnalyticsBox } from "@esg/components/esg_dashboard/esg_carbon_analytics_box/esg_carbon_analytics_box";
import { EsgCarbonFootprintBox } from "@esg/components/esg_dashboard/esg_carbon_footprint_box/esg_carbon_footprint_box";
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { rpc } from "@web/core/network";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions";

export class EsgDashboard extends Component {
    static template = "esg.Dashboard";
    static components = { EsgCarbonAnalyticsBox, EsgCarbonFootprintBox };
    static props = { ...standardActionServiceProps };
    props = useProps(this.constructor.props);

    setup() {
        this.ui = useService("ui");
        let showInfo = JSON.parse(
            browser.localStorage.getItem("showESGDashboardOnboardingTips"),
        );
        if (showInfo === null) {
            showInfo = true;
            browser.localStorage.setItem("showESGOnboardingTips", showInfo);
        }
        this.state = proxy({
            showInfo: showInfo,
        });
        onWillStart(async () => {
            this.data = await rpc("/esg/dashboard", {
                company_ids: user.context.allowed_company_ids,
            });
        });
    }

    toggleInfo() {
        browser.localStorage.setItem(
            "showESGDashboardOnboardingTips",
            !this.state.showInfo,
        );
        this.state.showInfo = !this.state.showInfo;
    }

    get dashboardComponents() {
        return {
            0: {
                component: EsgCarbonAnalyticsBox,
                props: {
                    data: this.data.carbon_analytics_box,
                },
            },
            1: {
                component: EsgCarbonFootprintBox,
                props: {
                    data: this.data.carbon_footprint_box,
                },
            },
        };
    }

    get dashboardContent() {
        return Object.values(this.dashboardComponents).filter(
            (item) => item.props.data != null,
        );
    }
}

registry.category("actions").add("action_esg_dashboard", EsgDashboard);
