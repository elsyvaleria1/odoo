/** @odoo-module native */
import { formatFieldDateTime } from "@web/core/formatters";
import { parseDateTime } from "@web/core/l10n/dates";
import { Time } from "@web/core/l10n/time";
import { MapRenderer } from "@web_map/map_view/map_renderer";

export class FsmTaskMapRenderer extends MapRenderer {
    static subTemplates = {
        ...MapRenderer.subTemplates,
        PinListItems: "industry_fsm.FsmTaskMapRenderer.PinListItems",
    };

    getFormattedTime(record) {
        const { date_start } = record;
        if (!date_start) {
            return "";
        }
        const datetime = parseDateTime(record.date_start);
        const time = Time.from({
            hour: datetime.hour,
            minute: datetime.minute,
            second: datetime.second,
        });
        if (time) {
            return time.toString(false);
        }
        return formatFieldDateTime(datetime, { showDate: false, showSeconds: false });
    }
}
