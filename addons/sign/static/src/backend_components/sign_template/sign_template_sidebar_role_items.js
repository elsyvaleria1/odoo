/** @odoo-module native */
import { Component, onWillUpdateProps, proxy, t, useProps } from "@odoo/owl";
import { Dropdown, DropdownItem } from "@web/components/dropdown";
import { RecordSelector } from "@web/components/record_selectors";
import { _t } from "@web/core/translation";
import { elementRef } from "@web/core/utils/element_ref";
import { useService } from "@web/core/utils/hooks";
import { fileTypeMagicWordMap } from "@web/fields/media/image/image_field";
import { ConfirmationDialog } from "@web/ui/dialog";
import { FormViewDialog } from "@web/views/view_dialogs";

export const signTemplateSidebarRoleItemsProps = {
    signItemTypes: t.array(),
    id: t.number(),
    name: t.string(),
    signTemplateId: t.number(),
    isSignRequest: t.boolean(),
    updateRoleName: t.function(),
    roleId: t.number().optional(),
    colorId: t.number(),
    isInputFocused: t.boolean().optional(),
    isCollapsed: t.boolean(),
    updateCollapse: t.function(),
    onDelete: t.function(),
    itemsCount: t.number(),
    hasSignRequests: t.boolean(),
    onFieldNameInputKeyUp: t.function(),
    assignTo: t.string().optional(),
};

export class SignTemplateSidebarRoleItems extends Component {
    static template = "sign.SignTemplateSidebarRoleItems";
    static components = {
        RecordSelector,
        Dropdown,
        DropdownItem,
    };
    static props = signTemplateSidebarRoleItemsProps;
    props = useProps(this.constructor.props);

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.roleInputRef = elementRef();
        const profilePic = this.getImageSrc(this.props.assignTo);
        this.state = proxy({
            roleName: this.props.name,
            canEditSignerName: false,
            profilePic: profilePic || "",
        });
        this.icon_type = {
            signature: "fa-solid fa-pen-to-square",
            initial: "fa-solid fa-pen-to-square",
            stamp: "fa-solid fa-pen-to-square",
            text: "fa-solid fa-font",
            textarea: "fa-solid fa-bars",
            checkbox: "fa-regular fa-square-check",
            radio: "fa-regular fa-circle-dot",
            selection: "fa-solid fa-angle-down",
            strikethrough: "fa-solid fa-strikethrough",
        };
        onWillUpdateProps((nextProps) => {
            if (nextProps.name !== this.state.roleName) {
                this.state.roleName = nextProps.name;
            }
        });
    }

    async onDeleteDialog() {
        const hasItems = this.props.itemsCount > 0;
        if (!hasItems) {
            this.props.onDelete();
        } else {
            this.dialog.add(ConfirmationDialog, {
                title: _t('Delete signer "%s"', this.state.roleName),
                body: _t("Do you really want to delete this signer?"),
                confirmLabel: _t("Delete"),
                confirm: () => {
                    this.props.onDelete();
                },
                cancel: () => {},
            });
        }
    }

    onSignerNameTextClick() {
        if (!this.props.hasSignRequests && !this.props.isCollapsed) {
            this.state.canEditSignerName = true;
            const input = this.roleInputRef.el;

            const waitForVisibility = () => {
                if (
                    input &&
                    !input.parentElement.parentElement.classList.contains("d-none")
                ) {
                    input.focus();
                    input.select();
                } else {
                    requestAnimationFrame(waitForVisibility);
                }
            };

            waitForVisibility();
        }
    }

    onSignerNameInputBlur() {
        this.state.canEditSignerName = false;
    }

    onChangeRoleName(name) {
        if (name && this.props.roleId && name !== this.state.roleName) {
            this.state.roleName = name;
            this.props.updateRoleName(this.props.roleId, this.state.roleName);
        }
    }

    onExpandSigner(id) {
        if (this.props.isCollapsed) {
            this.props.updateCollapse(id, false);
        }
    }

    async updateRoleNameAndAvatar(data) {
        this.onChangeRoleName(data.name);
        const assignToId = data.assign_to?.id;
        if (assignToId) {
            const [partner] = await this.orm.call("res.partner", "read", [
                [assignToId],
                ["avatar_128", "avatar_1920"],
            ]);
            const avatar = partner.avatar_128 || partner.avatar_1920;
            if (avatar) {
                this.state.profilePic = this.getImageSrc(avatar);
            }
        } else {
            this.state.profilePic = "";
        }
    }

    async openSignRoleRecord() {
        this.dialog.add(FormViewDialog, {
            resId: this.props.roleId,
            resModel: "sign.item.role",
            size: "md",
            title: _t("Signer Settings"),
            onRecordSaved: async ({ data }) => {
                this.state.canEditSignerName = true;
                await this.updateRoleNameAndAvatar(data);
            },
        });
    }

    getImageSrc(assignTo) {
        if (!assignTo) {
            return;
        }
        const magicChar = assignTo[0];
        const format = fileTypeMagicWordMap[magicChar] || "png";
        return `data:image/${format};base64,${assignTo}`;
    }
}
