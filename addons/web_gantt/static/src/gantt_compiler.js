/** @odoo-module native */
import { RECORD_TEMPLATE_DIRECTIVES, ViewCompiler } from "@web/views/view_compiler";

export class GanttCompiler extends ViewCompiler {}
GanttCompiler.OWL_DIRECTIVE_WHITELIST = [
    ...ViewCompiler.OWL_DIRECTIVE_WHITELIST,
    ...RECORD_TEMPLATE_DIRECTIVES,
];
