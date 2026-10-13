/** @odoo-module native */
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { listView } from "@web/views/list";

import { CalendarListController } from "./calendar_list_controller.js";

export class CalendarListModel extends listView.Model {
    setup(params) {
        super.setup(...arguments);
    }

    /** @override */
    async load(params = {}) {
        const filters = params?.context?.calendar_filters;
        const emptyDomain = Array.isArray(params?.domain) && params.domain.length === 0;
        if (filters && emptyDomain) {
            const selectedPartnerIds = await this.orm.call(
                "res.users",
                "get_selected_calendars_partner_ids",
                [[user.userId], filters["user"]],
            );
            if (!filters["all"]) {
                params.domain = [
                    ...params.domain,
                    ["partner_ids", "in", selectedPartnerIds],
                ];
            }
        }
        return super.load(params);
    }
}

export const CalendarListView = {
    ...listView,
    Model: CalendarListModel,
    Controller: CalendarListController,
};

function _mockGetCalendarPartnerIds(params) {
    return [];
}

registry.category("views").add("calendar_list_view", CalendarListView);
registry
    .category("sample_server")
    .add("get_selected_calendars_partner_ids", _mockGetCalendarPartnerIds);
