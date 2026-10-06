import {
    ProductProduct,
    SaleOrderLine,
} from "@sale_project/../tests/project_task_model";
import { defineTimesheetModels as defineTimesheetGridModels } from "@timesheet_grid/../tests/hr_timesheet_models";
import { defineModels } from "@web/../tests/web_test_helpers";

export function defineTimesheetModels() {
    defineTimesheetGridModels();
    defineModels([SaleOrderLine, ProductProduct]);
}
