/** @odoo-module native */
import { SURVEY_CHART_COLORS } from "@web/core/colors/colors";
import { colorToRgb } from "@web/core/utils/format/colors";

export default SURVEY_CHART_COLORS.map((color) =>
    colorToRgb(color).replaceAll(" ", ""),
);
