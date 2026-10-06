/** @odoo-module native */
import { TimesheetTimerListRenderer } from "@timesheet_grid/views/timesheet_list/timesheet_timer_list_renderer";

import { patchRenderer } from "../patch_renderer.js";

patchRenderer(TimesheetTimerListRenderer);
