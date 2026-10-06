import base64
from datetime import datetime, time, timedelta

from odoo import api, fields, models
from odoo.exceptions import RedirectWarning
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

# Set by the Delivered button: once the photo is in, the dialog delivers again.
# Any other caller validates on its own terms (quantities, backorders, context),
# so the dialog only keeps the photo and the caller repeats its action.
DELIVERY_PROOF_RESUME = "delivery_proof_resume"
# The photo is shrunk to this on upload: a phone photo of a sheet stays legible
# at a fraction of its size.
DELIVERY_PROOF_MAX_SIDE = 1920
# What shows the customer received a delivery: the photo of the signed slip, or
# the customer's signature captured on a screen.
DELIVERY_EVIDENCE = ("delivery_proof", "signature")


class StockPickingType(models.Model):
    _inherit = "stock.picking.type"

    delivery_proof_required = fields.Boolean(
        string="Require Signed Delivery Slip",
        tracking=True,
        help="Outgoing transfers of this type are validated only with a photo of "
        "the delivery slip signed by the customer, whoever validates them.",
    )
    delivery_paper_days = fields.Integer(
        string="Days to Hand In the Signed Slip",
        default=3,
        help="Working days, on the company's calendar, whoever delivered has to "
        "hand the signed delivery slip in on paper; past them they are reminded "
        "every day. Zero sends no reminder.",
    )
    delivery_proof_since = fields.Datetime(
        string="Required Since",
        tracking=True,
        help="Deliveries validated from this moment on are reviewed for their "
        "signed slip; earlier ones were validated without it. Set when the "
        "requirement is switched on, unless a date is given.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        picking_types = super().create(vals_list)
        picking_types._start_delivery_proof()
        return picking_types

    def write(self, vals):
        res = super().write(vals)
        if vals.get("delivery_proof_required"):
            self._start_delivery_proof()
        return res

    def _start_delivery_proof(self) -> None:
        """Date the requirement on the types that switch it on without a date."""
        self.filtered(
            lambda picking_type: (
                picking_type.delivery_proof_required
                and not picking_type.delivery_proof_since
            )
        ).delivery_proof_since = fields.Datetime.now()


class StockPicking(models.Model):
    _inherit = "stock.picking"
    # Who reviews the evidence of a delivery is its verbs' rows
    # (security/ir_access.xml): whoever delivers uploads the photo, but may not
    # vouch for it nor for the paper, nor rewrite the evidence once delivered.
    _access_verbs = {
        "reject_delivery_proof": models.Verb(
            transition=("delivery_proof_ok", True, False), at_create=False
        ),
        "accept_delivery_proof": models.Verb(
            transition=("delivery_proof_ok", False, True), at_create=False
        ),
        "receive_delivery_paper": models.Verb(
            transition=("delivery_paper_received", False, True), at_create=False
        ),
        "return_delivery_paper": models.Verb(
            transition=("delivery_paper_received", True, False), at_create=False
        ),
        "change_delivery_evidence": models.Verb(
            checkpoints=("_change_delivery_evidence",),
        ),
    }

    delivery_proof_required = fields.Boolean(
        related="picking_type_id.delivery_proof_required",
    )
    # Not the related above: it follows the type as it is today, so the reviewers'
    # lists would take every delivery the type ever validated.
    delivery_proof_due = fields.Boolean(
        string="Signed Slip Due",
        compute="_compute_delivery_proof_due",
        search="_search_delivery_proof_due",
        help="Validated since its operation type requires the signed slip, so it "
        "is reviewed for it.",
    )
    delivery_proof = fields.Image(
        string="Signed Delivery Slip",
        max_width=DELIVERY_PROOF_MAX_SIDE,
        max_height=DELIVERY_PROOF_MAX_SIDE,
        copy=False,
        help="Photo of the delivery slip signed by the customer, taken by whoever "
        "delivered the goods.",
    )
    delivery_proof_uid = fields.Many2one(
        comodel_name="res.users",
        string="Evidence Captured by",
        copy=False,
        readonly=True,
    )
    delivery_proof_date = fields.Datetime(
        string="Evidence Captured on",
        copy=False,
        readonly=True,
    )
    delivery_proof_ok = fields.Boolean(
        string="Valid Evidence",
        compute="_compute_delivery_proof_ok",
        store=True,
        copy=False,
        readonly=False,
        tracking=True,
        help="Ticked by itself when the photo of the signed slip or the customer's "
        "signature is captured. A reviewer unticks it when the evidence does not "
        "show this delivery signed by the customer, and whoever captured it is "
        "asked for the photo of the signed slip.",
    )
    delivery_paper_received = fields.Boolean(
        string="Received on Paper",
        copy=False,
        tracking=True,
        help="A reviewer ticks it with the signed delivery slip in hand.",
    )
    delivery_paper_received_uid = fields.Many2one(
        comodel_name="res.users",
        string="Paper Received by",
        copy=False,
        readonly=True,
    )
    delivery_paper_received_date = fields.Datetime(
        string="Paper Received on",
        copy=False,
        readonly=True,
    )

    # What is there, not whether it counts: whether a signature carries a name
    # that is not ours is judged when the delivery is validated, and the stored
    # tick must not depend on who triggers its recompute.
    @api.depends("delivery_proof", "signature")
    def _compute_delivery_proof_ok(self):
        for picking in self:
            picking.delivery_proof_ok = bool(
                picking.delivery_proof or picking.signature
            )

    @api.depends(
        "date_done",
        "picking_type_id.delivery_proof_required",
        "picking_type_id.delivery_proof_since",
    )
    def _compute_delivery_proof_due(self) -> None:
        for picking in self:
            since = picking.picking_type_id.delivery_proof_since
            picking.delivery_proof_due = bool(
                picking.picking_type_id.delivery_proof_required
                and since
                and picking.date_done
                and picking.date_done >= since
            )

    def _search_delivery_proof_due(self, operator, value):
        if operator != "in" or set(value) != {True}:
            return NotImplemented
        picking_types = self.env["stock.picking.type"].search(
            [
                ("delivery_proof_required", "=", True),
                ("delivery_proof_since", "!=", False),
            ]
        )
        return Domain.OR(
            Domain("picking_type_id", "=", picking_type.id)
            & Domain("date_done", ">=", picking_type.delivery_proof_since)
            for picking_type in picking_types
        )

    def write(self, vals):
        evidence = [fname for fname in DELIVERY_EVIDENCE if fname in vals]
        if evidence:
            self._guard_delivery_evidence(vals, evidence)
        if any(vals[fname] for fname in evidence):
            vals = {
                **vals,
                "delivery_proof_uid": self.env.uid,
                "delivery_proof_date": fields.Datetime.now(),
            }
        if "delivery_paper_received" in vals:
            received = bool(vals["delivery_paper_received"])
            vals = {
                **vals,
                "delivery_paper_received_uid": self.env.uid if received else False,
                "delivery_paper_received_date": (
                    fields.Datetime.now() if received else False
                ),
            }
        rejected = self.browse()
        if "delivery_proof_ok" in vals and not vals["delivery_proof_ok"]:
            rejected = self.filtered("delivery_proof_ok")
        res = super().write(vals)
        if evidence and not any(vals[fname] for fname in evidence):
            # Who captured the evidence is forgotten only with the last of it.
            self.filtered(
                lambda picking: (
                    picking.delivery_proof_uid
                    and not picking.delivery_proof
                    and not picking.signature
                )
            ).write({"delivery_proof_uid": False, "delivery_proof_date": False})
        # Evidence cleared together with its tick is not a rejection.
        rejected.filtered(
            lambda picking: picking.delivery_proof or picking.signature
        )._ask_for_another_delivery_proof()
        return res

    def _guard_delivery_evidence(self, vals, evidence) -> None:
        """Keep the evidence of a delivered transfer as it was reviewed.

        Once a delivery under review is done, whoever delivered may still add the
        photo it lacks or replace one a reviewer rejected; anything else (another
        signature, replacing or clearing what was accepted) is a reviewer's. What
        is replaced or cleared stays on the chatter.

        :param dict vals: the values being written
        :param list evidence: the evidence fields among them
        """
        delivered = self.filtered(
            lambda picking: picking.state == "done" and picking.delivery_proof_due
        )
        if not delivered:
            return
        reviewed = delivered.filtered(
            lambda picking: not picking._adds_delivery_proof(vals, evidence)
        )
        reviewed._change_delivery_evidence(evidence)
        (delivered - reviewed)._keep_delivery_evidence(evidence)

    def _adds_delivery_proof(self, vals, evidence) -> bool:
        """Whether this write only gives the transfer the photo it lacks.

        :rtype: bool
        """
        self.check_singleton()
        if evidence != ["delivery_proof"] or not vals["delivery_proof"]:
            return False
        return not self.delivery_proof or not self.delivery_proof_ok

    def _change_delivery_evidence(self, evidence) -> None:
        """A reviewer rewrites the evidence of a delivered transfer.

        :param list evidence: the evidence fields being written
        """
        self._keep_delivery_evidence(evidence)

    def _keep_delivery_evidence(self, evidence) -> None:
        """Post on the chatter the evidence about to be replaced or cleared.

        A rejection the write is about to lift, since the tick follows the
        evidence, is said there too.

        :param list evidence: the evidence fields being written
        """
        labels = self.fields_get(evidence, ["string"])
        for picking in self:
            attachments = [
                (
                    f"{picking.name} - {labels[fname]['string']}",
                    base64.b64decode(picking[fname]),
                )
                for fname in evidence
                if picking[fname]
            ]
            rejected = not picking.delivery_proof_ok and any(
                picking[fname] for fname in DELIVERY_EVIDENCE
            )
            if rejected:
                body = self.env._(
                    "The evidence a reviewer had rejected was replaced or cleared."
                )
            elif attachments:
                body = self.env._("Evidence before it was replaced or cleared.")
            else:
                continue
            picking.message_post(body=body, attachments=attachments)

    def _ask_for_another_delivery_proof(self):
        """Ask whoever captured the rejected evidence for the signed slip's photo."""
        for picking in self:
            uploader = picking.delivery_proof_uid
            if not uploader.active or uploader == self.env.user:
                continue
            _debug.logic("delivery_proof_rejected", picking=picking, uploader=uploader)
            picking.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=uploader.id,
                summary=self.env._("Upload the signed delivery slip again"),
                note=self.env._(
                    "The evidence of %(name)s was rejected: it does not show its "
                    "delivery signed by the customer.",
                    name=picking.name,
                ),
            )

    def _requires_delivery_proof(self):
        """Whether this transfer is validated only with the signed slip's photo.

        :rtype: bool
        """
        self.check_singleton()
        picking_type = self.picking_type_id
        return bool(
            picking_type.code == "outgoing"
            and picking_type.delivery_proof_required
            and not ("pos_session_id" in self._fields and self.pos_session_id)
        )

    def _has_delivery_proof(self):
        """Whether the transfer carries the customer's signature.

        Here, the photo of the delivery slip signed by the customer. A bridge that
        captures the signature another way, with who signed, adds its own.

        :rtype: bool
        """
        self.check_singleton()
        return bool(self.delivery_proof)

    def _check_dispatch_requirements(self):
        super()._check_dispatch_requirements()
        self._check_delivery_proof()

    def _check_delivery_proof(self):
        """Refuse to validate a transfer that needs the signed slip without it.

        The refusal carries the way out: a dialog that takes the photo and, for
        the Delivered button, delivers again.
        """
        missing = self.filtered(
            lambda picking: (
                picking._requires_delivery_proof() and not picking._has_delivery_proof()
            )
        )
        if not missing:
            return
        _debug.logic("delivery_proof_missing", pickings=missing)
        resume = (
            self.env.context.get(DELIVERY_PROOF_RESUME) if len(self) == 1 else False
        )
        raise RedirectWarning(
            self.env._(
                "%(pickings)s cannot be validated without the photo of the delivery "
                "slip signed by the customer.",
                pickings=", ".join(missing.mapped("name")),
            ),
            missing[:1]._action_upload_delivery_proof(resume),
            self.env._("Upload the signed slip"),
        )

    def _action_upload_delivery_proof(self, resume=False):
        """The dialog that takes the photo of the signed slip.

        :param resume: "deliver" to deliver once the photo is in, False to only
            keep it
        :rtype: dict
        """
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Signed Delivery Slip"),
            "res_model": "wizard.stock.picking.delivery.proof",
            "view_mode": "form",
            # A RedirectWarning hands the action to the client as is, with no
            # server pass to derive its views from view_mode.
            "views": [(False, "form")],
            "target": "new",
            "context": {
                "default_picking_id": self.id,
                "default_resume": resume,
            },
        }

    def action_deliver(self):
        # Missing its photo, the delivery is refused with a dialog that takes the
        # photo and delivers again: the whole transfer, as this button does.
        return super(
            StockPicking, self.with_context(**{DELIVERY_PROOF_RESUME: "deliver"})
        ).action_deliver()

    def action_receive_delivery_paper(self):
        """Tick the signed slips a reviewer has in hand, of delivered transfers."""
        self.filtered(
            lambda picking: (
                picking.state == "done" and not picking.delivery_paper_received
            )
        ).write({"delivery_paper_received": True})

    def _get_delivery_paper_due_date(self):
        self.check_singleton()
        days = self.picking_type_id.delivery_paper_days
        if not self.date_done or days <= 0:
            return None
        start = datetime.combine(self.date_done.date() + timedelta(days=1), time.min)
        calendar = self.company_id.resource_calendar_id
        due = calendar and calendar.plan_days(days, start, compute_leaves=True)
        return due.date() if due else self.date_done.date() + timedelta(days=days)

    def _get_delivery_paper_holder(self):
        self.check_singleton()
        return (
            self.delivery_proof_uid or self.batch_id.operator_id.user_id or self.user_id
        )

    def _cron_remind_delivery_paper(self) -> None:
        today = fields.Date.context_today(self)
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        pending = self.search(
            [
                ("delivery_proof_due", "=", True),
                ("delivery_paper_received", "=", False),
                ("picking_type_id.delivery_paper_days", ">", 0),
            ]
        )
        for picking in pending:
            due = picking._get_delivery_paper_due_date()
            holder = picking._get_delivery_paper_holder()
            if (
                not due
                or due >= today
                or not holder
                or picking.activity_ids.filtered(
                    lambda activity, holder=holder: (
                        activity.activity_type_id == activity_type
                        and activity.user_id == holder
                    )
                )
            ):
                continue
            picking.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                date_deadline=today,
                summary=self.env._("Hand in the signed delivery slip"),
                note=self.env._(
                    "Delivered on %(date)s; the signed slip was due on paper by "
                    "%(due)s.",
                    date=picking.date_done.date(),
                    due=due,
                ),
                user_id=holder.id,
            )
