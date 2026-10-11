/** @odoo-module native */
import { BaseOptionComponent, useDomState } from "@html_builder/core/utils";
import { t } from "@odoo/owl";

export class BorderConfigurator extends BaseOptionComponent {
    static template = "html_builder.BorderConfiguratorOption";
    static dependencies = ["builderActions"];
    static props = {
        label: t.string(),
        direction: t.string().optional(),
        withRoundCorner: t.boolean().optional(true),
        withBSClass: t.boolean().optional(true),
        action: t.string().optional("styleAction"),
    };

    setup() {
        super.setup();
        this.state = useDomState((editingElement) => ({
            hasBorder: this.hasBorder(editingElement),
        }));
    }
    getStyleActionParam(param) {
        const property = `border-${this.props.direction ? this.props.direction + "-" : ""}${param}`;
        if (this.props.withBSClass && (param === "width" || param === "radius")) {
            return `--box-${property}`;
        }
        return property;
    }
    hasBorder(editingElement) {
        const { getAction } = this.dependencies.builderActions;
        const styleActionValue = getAction("styleAction").getValue({
            editingElement,
            params: {
                mainParam: this.getStyleActionParam("width"),
            },
        });
        const values = (styleActionValue || "0").match(/\d+/g);
        return values.some((value) => parseInt(value) > 0);
    }
}
