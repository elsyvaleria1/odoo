/** @odoo-module native */
import { workLocationPresence } from "@hr_homeworking/work_location_presence";
import { AvatarCardResourcePopover } from "@resource_mail/components/avatar_card_resource/avatar_card_resource_popover";
import { patch } from "@web/core/utils/patch";

patch(AvatarCardResourcePopover.prototype, {
    get workLocation() {
        return workLocationPresence(this.record?.im_status);
    },
});
