/** @odoo-module native */
import { registry } from "@web/core/registry";
import { formView } from "@web/views/form";

import { JobPostNoSaveFormController } from "./job_post_no_save_controller.js";

registry.category("views").add("job_post_no_save_form", {
    ...formView,
    Controller: JobPostNoSaveFormController,
});
