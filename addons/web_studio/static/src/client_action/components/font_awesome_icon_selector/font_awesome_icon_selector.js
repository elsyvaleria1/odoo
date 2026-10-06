/** @odoo-module native */
import { Component, t, useProps } from "@odoo/owl";
import { SelectMenu } from "@web/components/select_menu";
import { getFontAwesomeIcons } from "@web_studio/utils";

export class FontAwesomeIconSelector extends Component {
    static template = "web_studio.FontAwesomeIconSelector";
    static props = {
        className: t.string().optional(""),
        menuClassName: t.string().optional(""),
        value: t.string(),
        onSelect: t.function().optional(),
        slots: t.any(),
    };
    static components = { SelectMenu };
    props = useProps(this.constructor.props);

    setup() {
        this.ICONS = getFontAwesomeIcons();
    }

    get iconChoices() {
        return this.ICONS.map((icon) => ({
            label: icon.searchTerms.join(" "),
            value: icon.className,
        }));
    }

    getIconTooltip(value) {
        return this.ICONS.find((icon) => icon.className === value).tooltip;
    }
}
