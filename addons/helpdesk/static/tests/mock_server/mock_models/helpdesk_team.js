import { fields, models } from "@web/../tests/web_test_helpers";

export class HelpdeskTeam extends models.Model {
    _name = "team.team";

    name = fields.Char();
    helpdesk_use_sla = fields.Boolean({ string: "Use SLA" });
    helpdesk_use_alias = fields.Boolean({ string: "Use Alias" });
    use_helpdesk_timesheet = fields.Boolean({ string: "Use Timesheet" });
    helpdesk_stage_ids = fields.Many2many({ relation: "helpdesk.stage" });

    _records = [
        { id: 1, name: "Team 1", helpdesk_use_sla: true, helpdesk_use_alias: true },
        { id: 2, name: "Team 2", helpdesk_use_alias: true },
    ];
}
