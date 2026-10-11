from odoo import fields, models

CONDITIONS = [
    ("always", "Always"),
    ("hold_active", "A hold is open on the profile"),
    ("exception_active", "A dated exception is running"),
    ("state_is", "Profile state is the one named"),
    ("documents_noncompliant", "Required documents missing or expired"),
    ("overdue_amount_over", "Overdue receivable above the threshold"),
    ("overdue_days_over", "Oldest overdue past the threshold in days"),
    ("limit_exceeded", "Exposure plus the document exceeds the credit limit"),
    ("term_over_max", "Payment term longer than the grade allows"),
    ("no_grade", "No grade assigned"),
]
DOCUMENT_KINDS = [
    ("any", "Orders and invoices"),
    ("order", "Sale order"),
    ("invoice", "Customer invoice"),
    ("picking", "Delivery"),
]
PAYMENT_KINDS = [
    ("any", "Any payment term"),
    ("credit", "Credit terms only"),
    ("immediate", "Immediate payment only"),
]
OUTCOMES = [
    ("allow", "Allow"),
    ("warn", "Allow with a warning"),
    ("approve", "Requires a credit manager's authorization"),
    ("block", "Block"),
]
PROFILE_STATES = [
    ("cash", "Cash Only"),
    ("active", "Active"),
    ("watch", "Watch"),
    ("default", "Default"),
    ("legal", "Legal Process"),
]


class CreditPolicyRule(models.Model):
    _name = "credit.policy.rule"
    _description = "Credit Policy Rule"
    _order = "sequence, id"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one(
        comodel_name="res.company",
        help="Empty applies to every company.",
    )
    document_kind = fields.Selection(
        selection=DOCUMENT_KINDS,
        default="any",
        required=True,
    )
    payment_kind = fields.Selection(
        selection=PAYMENT_KINDS,
        default="credit",
        required=True,
    )
    condition = fields.Selection(
        selection=CONDITIONS,
        required=True,
    )
    state = fields.Selection(
        selection=PROFILE_STATES,
        help="For the 'Profile state is the one named' condition.",
    )
    threshold = fields.Float(
        help="Amount or days the condition compares against.",
    )
    grade_ids = fields.Many2many(
        comodel_name="credit.grade",
        relation="credit_policy_rule_grade_rel",
        help="Empty applies to every grade.",
    )
    outcome = fields.Selection(
        selection=OUTCOMES,
        required=True,
    )
    stop = fields.Boolean(
        help="When this rule applies, no later rule is read. Used for an "
        "explicit allowance such as a running exception.",
    )
    message = fields.Char(
        translate=True,
        help="Shown to the user; %(partner)s, %(amount)s, %(days)s, %(limit)s, "
        "%(exposure)s are substituted.",
    )

    def _applies(self, profile, facts):
        self.check_singleton()
        if facts["kind"] == "picking":
            if self.document_kind != "picking":
                return False
        elif self.document_kind != "any" and self.document_kind != facts["kind"]:
            return False
        if self.payment_kind == "credit" and facts["immediate"]:
            return False
        if self.payment_kind == "immediate" and not facts["immediate"]:
            return False
        if self.grade_ids and profile.grade_id not in self.grade_ids:
            return False
        return self._condition_holds(profile, facts)

    def _condition_holds(self, profile, facts):
        match self.condition:
            case "always":
                return True
            case "hold_active":
                return facts["hold"]
            case "exception_active":
                return facts["exception"]
            case "state_is":
                return profile.state == self.state
            case "documents_noncompliant":
                return not profile.document_compliant
            case "overdue_amount_over":
                return facts["overdue"] > self.threshold
            case "overdue_days_over":
                return facts["overdue_days"] > self.threshold
            case "limit_exceeded":
                return facts["excess"] > 0
            case "term_over_max":
                grade = profile.grade_effective_id
                return bool(
                    grade
                    and grade.max_payment_term_days > 0
                    and facts["term_days"] > grade.max_payment_term_days
                )
            case "no_grade":
                return not profile.grade_id
        return False

    def _render(self, profile, facts):
        self.check_singleton()
        currency = profile.company_id.currency_id
        template = self.message or self.name
        return template % {
            "partner": profile.partner_id.name,
            "amount": currency.format(facts["amount"]),
            "days": facts["overdue_days"],
            "limit": currency.format(facts["limit"]),
            "exposure": currency.format(facts["exposure"]),
            "overdue": currency.format(facts["overdue"]),
        }
