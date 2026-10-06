/** @odoo-module native */
import { Component, proxy, t, useProps } from "@odoo/owl";
import { _t } from "@web/core/translation";
import { useService } from "@web/core/utils/hooks";
import { Many2XAutocomplete } from "@web/fields/relational/many2x_autocomplete";
import { Dialog } from "@web/ui/dialog";
import { FontAwesomeIconSelector } from "@web_studio/client_action/components/font_awesome_icon_selector/font_awesome_icon_selector";

export class NewButtonBoxDialog extends Component {
    static template = "web_studio.NewButtonBoxDialog";
    static components = {
        Dialog,
        FontAwesomeIconSelector,
        Many2XAutocomplete,
    };
    static props = {
        isAddingButtonBox: t.boolean(),
        model: t.object(),
        close: t.function(),
    };
    props = useProps(this.constructor.props);
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = proxy({
            icon: "fa-regular fa-gem",
            field: undefined,
        });
        this.text = undefined;
    }
    async update(selection) {
        if (!selection[0].display_name) {
            const resId = selection[0].id;
            const fields = ["display_name"];
            const record = await this.orm.read("ir.model.fields", [resId], fields);
            selection[0].display_name = record[0].display_name;
        }
        this.state.field = selection[0];
    }
    getDomain() {
        return [
            ["relation", "=", this.props.model.resModel],
            ["ttype", "in", ["many2one", "many2many"]],
            ["store", "=", true],
        ];
    }
    onConfirm() {
        if (!this.state.field?.id) {
            return this.notification.add(_t("Select a related field."));
        }
        if (this.props.isAddingButtonBox) {
            this.props.model.pushOperation({ type: "buttonbox" });
        }
        this.props.model.doOperation({
            type: "add",
            target: {
                tag: "div",
                attrs: {
                    class: "oe_button_box",
                },
            },
            position: "inside",
            node: {
                tag: "button",
                field: this.state.field.id,
                string: this.text || _t("New button"),
                attrs: {
                    class: "oe_stat_button",
                    // full "fa-<family> fa-<name>" string: iconFromString
                    // resolves it as-is when rendering the button
                    icon: this.state.icon,
                },
            },
        });
        this.props.close();
    }
}
