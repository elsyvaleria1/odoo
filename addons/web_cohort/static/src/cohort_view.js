/** @odoo-module native */
import { registry } from "@web/core/registry";

import { CohortArchParser } from "./cohort_arch_parser.js";
import { CohortController } from "./cohort_controller.js";
import { CohortModel } from "./cohort_model.js";
import { CohortRenderer } from "./cohort_renderer.js";

export const cohortView = {
    type: "cohort",
    buttonTemplate: "web_cohort.CohortView.Buttons",
    searchMenuTypes: ["filter", "favorite"],
    Model: CohortModel,
    ArchParser: CohortArchParser,
    Controller: CohortController,
    Renderer: CohortRenderer,

    modelParams: {
        fromState: (state) => state.metaData,
        fromArch: (archInfo, { fields, resModel }) => ({
            dateStart: archInfo.dateStart,
            dateStartString: archInfo.dateStartString,
            dateStop: archInfo.dateStop,
            dateStopString: archInfo.dateStopString,
            fieldAttrs: archInfo.fieldAttrs,
            fields,
            interval: archInfo.interval,
            measure: archInfo.measure,
            mode: archInfo.mode,
            resModel,
            timeline: archInfo.timeline,
            title: archInfo.title,
            disableLinking: Boolean(archInfo.disableLinking),
            widgets: archInfo.widgets,
        }),
    },
};

registry.category("views").add("cohort", cohortView);
