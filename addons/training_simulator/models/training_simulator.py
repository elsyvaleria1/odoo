from odoo import api, fields, models
from odoo.tools import frozendict


class TrainingSimulator(models.Model):
    _name = "training.simulator"
    _description = "Training Simulator"
    _order = "area, sequence, name"
    # one catalogue every company plays from
    _access_anchors = frozendict({"company": ""})

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(
        required=True,
        help="Technical key of the simulator; the module that implements it reads it.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    area = fields.Selection(
        selection=[
            ("logistics", "Logistics"),
            ("production", "Production"),
            ("quality", "Quality"),
            ("sales", "Sales"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    icon = fields.Char(
        default="🎮",
        help="Emoji shown on the simulator card.",
    )
    tagline = fields.Char(
        translate=True,
        help="One line on the card that says what the player gets out of it.",
    )
    description = fields.Text(translate=True)
    flow_steps = fields.Char(
        string="Flow steps",
        translate=True,
        help="Comma-separated steps the game walks through, shown on the card.",
    )
    play_route = fields.Char(
        required=True,
        help="Page of the game; it receives the session in the 'session' parameter.",
    )
    scenario_count = fields.Integer(
        default=1,
        help="Scenarios a player can pass; the progress counts them.",
    )
    session_ids = fields.One2many(
        comodel_name="training.simulator.session",
        inverse_name="simulator_id",
    )
    session_count = fields.Integer(compute="_compute_session_count")

    _code_unique = models.Constraint("UNIQUE(code)", "A simulator code is unique.")

    @api.depends("session_ids")
    def _compute_session_count(self):
        counts = dict(
            self.env["training.simulator.session"]._read_group(
                [("simulator_id", "in", self.ids)], ["simulator_id"], ["__count"]
            )
        )
        for simulator in self:
            simulator.session_count = counts.get(simulator, 0)

    def action_play(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": f"/training_simulator/{self.id}/play",
            "target": "self",
        }

    def action_view_sessions(self):
        self.check_singleton()
        action = self.env["ir.actions.act_window"]._get_action_dict_by_xml_id(
            "training_simulator.action_training_simulator_session"
        )
        action["domain"] = [("simulator_id", "=", self.id)]
        return action

    # ------------------------------------------------------------------
    # Training center
    # ------------------------------------------------------------------
    @api.model
    def get_training_dashboard(self):
        """What the training center shows the current user.

        :return: one card per simulator with the scenarios the user practised
        :rtype: dict
        """
        user = self.env.user
        sessions = self.env["training.simulator.session"].search(
            [("user_id", "=", user.id)]
        )
        done = sessions.filtered(lambda s: s.state == "done")
        simulators = self.search([])
        area_labels = dict(self._fields["area"]._description_selection(self.env))
        cards = []
        for simulator in simulators:
            # Learning progress, not a ranking: which scenarios this user has practised.
            mine = done.filtered(lambda s, sim=simulator: s.simulator_id == sim)
            best = len(set(mine.mapped("scenario")))
            last = sessions.filtered(lambda s, sim=simulator: s.simulator_id == sim)[:1]
            cards.append(
                {
                    "id": simulator.id,
                    "code": simulator.code,
                    "name": simulator.name,
                    "tagline": simulator.tagline or "",
                    "flow_steps": [
                        step.strip()
                        for step in (simulator.flow_steps or "").split(",")
                        if step.strip()
                    ],
                    "tags": simulator._training_card_tags(),
                    "icon": simulator.icon,
                    "area": simulator.area,
                    "area_label": area_labels.get(simulator.area),
                    "description": simulator.description or "",
                    "detail": simulator._training_card_detail(),
                    "scenario_count": simulator.scenario_count,
                    "best": min(best, simulator.scenario_count),
                    "last_played": fields.Datetime.to_string(last.date_start)
                    if last
                    else False,
                }
            )
        return {
            "user_name": user.name,
            "is_instructor": self.has_access("create"),
            "all_areas": [
                {"key": k, "label": v} for k, v in area_labels.items() if k != "other"
            ],
            "simulators": cards,
        }

    def _training_card_detail(self):
        """Short line under the simulator's name in the training center, e.g. its routes.

        :rtype: str
        """
        self.check_singleton()
        return ""

    def _training_card_tags(self):
        """Labelled chips on the simulator's card in the training center, e.g. its routes.

        :return: ``{"label": str, "items": [str]}``, or an empty dict for none
        :rtype: dict
        """
        self.check_singleton()
        return {}

    def _training_snapshot(self, session):
        """Real data the session plays on, read when it starts.

        Each simulator module overrides it for its code and reads with a read-only
        privilege, so building the snapshot cannot write anything either.

        :param session: the session that starts
        :return: JSON-serializable data the game page receives
        :rtype: dict
        """
        self.check_singleton()
        return {}
