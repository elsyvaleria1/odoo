/** @odoo-module native */
import { Component, status, t, useProps } from "@odoo/owl";
import { localization } from "@web/core/l10n/localization";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePopover } from "@web/ui/popover";
import { standardWidgetProps } from "@web/views/widgets";

export class CrmPlsTooltip extends Component {
    static props = {
        close: t.function().optional(),
        dashArrayVals: t.string(),
        low3Data: t.array().optional(),
        probability: t.number(),
        teamName: t.string().optional(),
        top3Data: t.array().optional(),
    };
    static template = "crm.PlsTooltip";
    props = useProps(this.constructor.props);
}

export class CrmPlsTooltipButton extends Component {
    static template = "crm.PlsTooltipButton";
    static props = { ...standardWidgetProps };
    props = useProps(this.constructor.props);

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.popover = usePopover(CrmPlsTooltip, {
            class: "mt-2 me-2",
            position: "bottom-start",
        });
    }

    async onClickPlsTooltipButton(ev) {
        const tooltipButtonEl = ev.currentTarget;
        if (this.popover.isOpen) {
            this.popover.close();
        } else {
            await this.props.record.save();
            if (status(this) === "destroyed" || !this.props.record.resId) {
                return;
            }

            const tooltipData = await this.orm.call(
                "crm.lead",
                "update_and_get_pls_tooltip_data",
                [this.props.record.resId],
            );
            await this.props.record.load();

            const progressWheelPerimeter = 2 * Math.PI * 25;
            const progressBarDashLength =
                (progressWheelPerimeter * tooltipData.probability) / 100.0;
            const progressBarDashGap = progressWheelPerimeter - progressBarDashLength;
            let dashArrayVals = progressBarDashLength + " " + progressBarDashGap;
            if (localization.direction === "rtl") {
                dashArrayVals =
                    0 + " " + 0.5 * progressWheelPerimeter + " " + dashArrayVals;
            }
            this.popover.open(tooltipButtonEl, {
                dashArrayVals: dashArrayVals,
                low3Data: tooltipData.low_3_data,
                probability: tooltipData.probability,
                teamName: tooltipData.team_name,
                top3Data: tooltipData.top_3_data,
            });
        }
    }
}

registry.category("view_widgets").add("pls_tooltip_button", {
    component: CrmPlsTooltipButton,
});
