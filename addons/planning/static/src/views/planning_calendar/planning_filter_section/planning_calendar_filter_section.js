/** @odoo-module native */
import { RESOURCE_TYPE_ICONS } from "@web/components/resource_avatar/resource_type_icons";
import { CalendarFilterSection } from "@web/views/calendar";

export class PlanningCalendarFilterSection extends CalendarFilterSection {
    static template = "planning.PlanningCalendarFilterSection";
    static subTemplates = {
        filter: "planning.PlanningCalendarFilterSection.filter",
    };

    getNoColor(filter) {
        return this.section.fieldName === "resource_id" ? "no_filter_color" : "";
    }






    getSortedFilters() {
        const sortedFilters = super.getSortedFilters();
        let nullValueItem = false;
        for (const item of sortedFilters) {
            if (!item.value) {
                nullValueItem = item;
                break;
            }
        }
        if (nullValueItem) {
            sortedFilters.splice(sortedFilters.indexOf(nullValueItem), 1);
            sortedFilters.splice(0, 0, nullValueItem);
        }
        return sortedFilters;
    }




    async loadSource(request) {
        const options = await super.loadSource(request);
        if (this.section.fieldName !== "resource_id") {
            return options;
        }
        const resourceIds = options.map((option) => option.data?.id).filter(Boolean);
        const resources = await this.orm.read("resource.resource", resourceIds, [
            "type",
        ]);
        const typeById = Object.fromEntries(
            resources.map(({ id, type }) => [id, type]),
        );
        for (const option of options) {
            if (option.data?.id) {
                option.data.resourceType = typeById[option.data.id];
            }
        }
        return options;
    }

    typeIcon(type) {
        return RESOURCE_TYPE_ICONS[type];
    }
}
