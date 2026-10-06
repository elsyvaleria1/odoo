import { planningModels } from "@planning/../tests/planning_mock_models";
import { defineModels } from "@web/../tests/web_test_helpers";

export function definePlanningHolidaysModels() {
    return defineModels(planningHolidaysModels);
}

export const planningHolidaysModels = { ...planningModels };
