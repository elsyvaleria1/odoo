import { hrModels } from "@hr/../tests/hr_test_helpers";
import { HrEmployee } from "@hr_work_entry/../tests/mock_server/mock_models/hr_employee";
import { HrWorkEntry } from "@hr_work_entry/../tests/mock_server/mock_models/hr_work_entry";
import { HrWorkEntryType } from "@hr_work_entry/../tests/mock_server/mock_models/hr_work_entry_type";
import { defineModels } from "@web/../tests/web_test_helpers";

export function defineHrWorkEntryModels() {
    return defineModels(hrWorkEntryModels);
}

export const hrWorkEntryModels = {
    ...hrModels,
    HrEmployee,
    HrWorkEntry,
    HrWorkEntryType,
};
