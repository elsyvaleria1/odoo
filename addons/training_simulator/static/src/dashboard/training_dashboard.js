/** @odoo-module native */
import { Component, onWillStart, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Layout } from "@web/search/layout";

class TrainingDashboard extends Component {
    static template = "training_simulator.Dashboard";
    static components = { Layout };
    static props = null;
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.display = { controlPanel: {} };
        this.state = proxy({ loading: true, data: null, area: "all", search: "" });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.data = await this.orm.call(
            "training.simulator",
            "get_training_dashboard",
            [],
        );
        this.state.loading = false;
    }

    get cards() {
        const term = this.state.search.trim().toLowerCase();
        return this.state.data.simulators.filter(
            (card) =>
                (this.state.area === "all" || card.area === this.state.area) &&
                (!term ||
                    `${card.name} ${card.tagline} ${card.description} ${card.detail}`
                        .toLowerCase()
                        .includes(term)),
        );
    }

    get emptyAreas() {
        const used = new Set(this.state.data.simulators.map((card) => card.area));
        return this.state.data.all_areas.filter(
            (area) =>
                !used.has(area.key) &&
                (this.state.area === "all" || this.state.area === area.key),
        );
    }

    play(card) {
        window.location.assign(`/training_simulator/${card.id}/play`);
    }

    openSessions(card) {
        return this.actionService.doAction(
            "training_simulator.action_training_simulator_session",
            {
                additionalContext: card
                    ? { search_default_simulator_id: card.id }
                    : { search_default_my: 1 },
            },
        );
    }

    openSimulator(card) {
        return this.actionService.doAction({
            type: "ir.actions.act_window",
            res_model: "training.simulator",
            res_id: card.id,
            views: [[false, "form"]],
        });
    }
}

registry.category("actions").add("training_simulator_dashboard", TrainingDashboard);
