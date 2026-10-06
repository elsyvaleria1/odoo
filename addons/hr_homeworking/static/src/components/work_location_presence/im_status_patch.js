/** @odoo-module native */
import { workLocationPresence } from "@hr_homeworking/work_location_presence";
import { ImStatus } from "@mail/core/common/im_status";
import { ThreadIcon } from "@mail/core/common/thread_icon";
import { patch } from "@web/core/utils/patch";

patch(ImStatus.prototype, {
    get workLocation() {
        return workLocationPresence(this.persona?.im_status);
    },
});

patch(ThreadIcon.prototype, {
    get workLocation() {
        return workLocationPresence(this.correspondent?.im_status);
    },
});
