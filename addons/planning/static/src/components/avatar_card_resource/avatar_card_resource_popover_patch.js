/** @odoo-module native */
import { AvatarCardResourcePopover } from "@resource_mail/components/avatar_card_resource/avatar_card_resource_popover";
import { patch } from "@web/core/utils/patch";

export const patchAvatarCardResourcePopover = {
    async onWillStart() {
        await super.onWillStart();
        this.roles = this.record.role_ids;
    },
    get fieldNames() {
        const additionalFields = ["role_ids"];
        const excludedFields = ["work_location_name", "work_location_type"];
        return [...super.fieldNames, ...additionalFields].filter(
            (field) => !excludedFields.includes(field),
        );
    },
    get roleTags() {
        const marksDefaultRole = this.roles.length > 1;
        const defaultRoleId = this.record.default_role_id?.[0];
        return this.roles.map(({ id, color, name }) => ({
            id,
            colorIndex: color,
            text: name,
            ...(marksDefaultRole && id === defaultRoleId ? { icon: "fa-star" } : {}),
            className: "o_planning_avatar_role_tag",
        }));
    },
    get hasFooter() {
        return this.roles?.length > 0 || super.hasFooter;
    },
};

export const unpatchAvatarCardResourcePopover = patch(
    AvatarCardResourcePopover.prototype,
    patchAvatarCardResourcePopover,
);
