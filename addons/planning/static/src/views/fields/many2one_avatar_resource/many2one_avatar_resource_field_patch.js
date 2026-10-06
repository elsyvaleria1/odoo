/** @odoo-module native */
import { AvatarCardResourcePopover } from "@resource_mail/components/avatar_card_resource/avatar_card_resource_popover";
import {
    KanbanMany2OneAvatarResourceField,
    kanbanMany2OneAvatarResourceField,
} from "@resource_mail/views/fields/many2one_avatar_resource/kanban_many2one_avatar_resource_field";
import {
    Many2OneAvatarResourceField,
    many2OneAvatarResourceField,
} from "@resource_mail/views/fields/many2one_avatar_resource/many2one_avatar_resource_field";
import { patch } from "@web/core/utils/patch";
import { usePopover } from "@web/ui/popover";

function patchFieldComponent(o) {
    patch(o, {
        setup() {
            super.setup();
            this.resourceIconPopover = usePopover(AvatarCardResourcePopover);
        },
        openResourceIconPopover(target) {
            if (
                !this.props.record.data[this.props.name] ||
                (!this.resourceIconPopover.isOpen &&
                    this.props.record.data.resource_roles?.currentIds.length <= 1)
            ) {
                return;
            }
            this.resourceIconPopover.open(target, {
                id: this.props.record.data[this.props.name].id,
                recordModel: this.props.record.fields[this.props.name].relation,
            });
        },
    });
}

patchFieldComponent(Many2OneAvatarResourceField.prototype);
patchFieldComponent(KanbanMany2OneAvatarResourceField.prototype);

function patchFieldDescr(o) {
    patch(o, {
        fieldDependencies: [
            ...o.fieldDependencies,
            {
                name: "resource_roles",
                type: "many2many",
            },
            {
                name: "resource_color",
                type: "integer",
            },
        ],
    });
}

patchFieldDescr(many2OneAvatarResourceField);
patchFieldDescr(kanbanMany2OneAvatarResourceField);
