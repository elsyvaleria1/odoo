import "@device_machines/dashboard/plc_dashboard";

import { expect, getFixture, test } from "@odoo/hoot";
import { loadChartJS } from "@web/core/lib/chartjs";
import { registry } from "@web/core/registry";

test("PLC chart datasets keep their colors after the palette wraps", async () => {
    await loadChartJS();
    const Dashboard = registry.category("actions").get("plc_dashboard");
    const dashboard = Object.create(Dashboard.prototype);
    dashboard.charts = {};
    const canvas = document.createElement("canvas");
    getFixture().append(canvas);
    try {
        dashboard.renderChart(
            "production",
            { el: canvas },
            {
                labels: ["Today"],
                datasets: Array.from({ length: 6 }, (_, i) => ({
                    label: String(i),
                    data: [i],
                })),
            },
        );
        expect(
            dashboard.charts.production.data.datasets.map((ds) => ds.backgroundColor),
        ).toEqual(["#017E84", "#5B899E", "#F4A261", "#E76F51", "#8E7CC3", "#017E84"]);
    } finally {
        dashboard.destroyCharts();
    }
});
