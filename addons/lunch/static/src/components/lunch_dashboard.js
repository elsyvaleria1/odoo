/** @odoo-module native */
import { Component, markup, onWillStart, proxy, t, useProps, xml } from "@odoo/owl";
import { DateTimeInput } from "@web/components/datetime";
import { today } from "@web/core/l10n/dates";
import { rpc } from "@web/core/network";
import { user } from "@web/core/user";
import { useBus, useEventBus, useService } from "@web/core/utils/hooks";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";
import { useSearchModel } from "@web/search/search_model";
import { Collapse } from "@web/ui/collapse/collapse";
import { Offcanvas } from "@web/ui/offcanvas/offcanvas";

export class LunchCurrency extends Component {
    static template = "lunch.LunchCurrency";
    static props = { currency: t.any(), amount: t.any() };
    props = useProps(this.constructor.props);

    get amount() {
        return parseFloat(this.props.amount).toFixed(2);
    }
}

export class LunchOrderLine extends Component {
    static template = "lunch.LunchOrderLine";
    static props = {
        line: t.any(),
        currency: t.any(),
        onUpdateQuantity: t.any(),
        openOrderLine: t.any(),
        infos: t.any(),
        isToOrder: t.any(),
    };
    static components = {
        LunchCurrency,
    };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state = proxy({ mobileOpen: false });
    }

    get line() {
        return this.props.line;
    }

    get canAdd() {
        let price = this.line.product[3];
        this.line.toppings.forEach((line) => (price += line[3]));
        const unpaid = parseFloat(this.props.infos.unpaid_subtotal);
        return this.canEdit && this.props.infos.wallet_with_config - unpaid >= price;
    }

    get canEdit() {
        return !["sent", "confirmed"].includes(this.line.raw_state);
    }

    get badgeClass() {
        const mapping = {
            new: "secondary",
            confirmed: "success",
            sent: "info",
            ordered: "primary",
        };
        return mapping[this.line.raw_state];
    }

    get hasToppings() {
        return this.line.toppings.length !== 0;
    }

    async updateQuantity(increment) {
        await this.orm.call("lunch.order", "update_quantity", [
            this.props.line.id,
            increment,
        ]);

        await this.props.onUpdateQuantity();
    }
}

export class LunchAlert extends Component {
    static props = { message: t.any() };
    static template = xml`<t t-out="this.message"/>`;
    props = useProps(this.constructor.props);
    get message() {
        return markup(this.props.message);
    }
}

export class LunchAlerts extends Component {
    static components = {
        LunchAlert,
    };
    static props = { alerts: t.any() };
    static template = "lunch.LunchAlerts";
    props = useProps(this.constructor.props);
}

export class LunchUser extends Component {
    static components = {
        Many2XAutocomplete,
    };
    static props = { username: t.any(), isManager: t.any(), onUpdateUser: t.any() };
    static template = "lunch.LunchUser";
    props = useProps(this.constructor.props);
    getDomain() {
        return [["share", "=", false]];
    }
}

export class LunchLocation extends Component {
    static components = {
        Many2XAutocomplete,
    };
    static props = { location: t.any(), onUpdateLunchLocation: t.any() };
    static template = "lunch.LunchLocation";
    props = useProps(this.constructor.props);
    getDomain() {
        return [];
    }
}

export class LunchDashboard extends Component {
    static components = {
        Collapse,
        LunchAlerts,
        LunchCurrency,
        LunchLocation,
        LunchOrderLine,
        LunchUser,
        Many2XAutocomplete,
        Offcanvas,
        DateTimeInput,
    };
    static props = { openOrderLine: t.any() };
    static template = "lunch.LunchDashboard";
    props = useProps(this.constructor.props);
    setup() {
        super.setup();
        this.bus = useEventBus();
        this.searchModel = useSearchModel();
        this.ui = useService("ui");
        this.state = proxy({
            infos: {},
            date: today(),
            passedOrdersOpen: false,
            cartOpen: false,
        });

        useBus(this.bus, "lunch_update_dashboard", () => this._fetchLunchInfos());
        onWillStart(async () => {
            await this._fetchLunchInfos();
            this.searchModel.updateLocationId(this.state.infos.user_location[0]);
        });
    }

    async lunchRpc(route, args = {}) {
        return await rpc(route, {
            ...args,
            context: user.context,
            user_id: this.searchModel.lunchState.userId,
        });
    }

    async _fetchLunchInfos() {
        this.state.infos = await this.lunchRpc("/lunch/infos");
    }

    async emptyCart() {
        await this.lunchRpc("/lunch/trash");
        await this._fetchLunchInfos();
    }

    get hasLines() {
        return this.state.infos.lines && this.state.infos.lines.length !== 0;
    }

    get canOrder() {
        return this.state.infos.raw_state === "new";
    }

    get location() {
        return this.state.infos.user_location && this.state.infos.user_location[1];
    }

    async orderNow() {
        if (!this.canOrder) {
            return;
        }

        await this.lunchRpc("/lunch/pay");
        await this._fetchLunchInfos();
    }

    async onUpdateQuantity() {
        await this._fetchLunchInfos();
    }

    async onUpdateUser(value) {
        if (!value) {
            return;
        }
        this.searchModel.updateUserId(value[0].id);
        await this._fetchLunchInfos();
    }

    async onUpdateLunchLocation(value) {
        if (!value) {
            return;
        }

        await this.lunchRpc("/lunch/user_location_set", {
            location_id: value[0].id,
        });
        await this._fetchLunchInfos();
        this.searchModel.updateLocationId(value[0].id);
    }

    async onUpdateLunchTime(value) {
        this.state.date = value || today();
        this.searchModel.updateDate(this.state.date);
    }
}
