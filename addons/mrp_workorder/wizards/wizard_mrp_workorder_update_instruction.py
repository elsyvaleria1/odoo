import re

from markupsafe import Markup

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

_debug = DebugLog(__name__)


class WizardMrpWorkorderUpdateInstruction(models.TransientModel):
    _name = "wizard.mrp.workorder.update.instruction"
    _description = "Propose a change in the production"

    IMG_REGEX = re.compile(r'(<img .*?">)')

    workorder_id = fields.Many2one(
        comodel_name="mrp.workorder",
        required=True,
        ondelete="cascade",
    )
    title = fields.Char()
    step_id = fields.Many2one(
        comodel_name="quality.check",
        string="Step to change",
    )
    note = fields.Html(string="New Instruction")
    comment = fields.Char()
    picture = fields.Binary()
    change_type = fields.Selection(
        selection=[
            ("update_step", "Update Current Step"),
            ("remove_step", "Remove Current Step"),
            ("set_picture", "Set Picture"),
        ],
        string="Type of Change",
    )

    @api.model
    def default_get(self, fields):
        defaults = super().default_get(fields)
        if "step_id" in defaults:
            step = self.env["quality.check"].browse(defaults.get("step_id"))
            defaults["title"] = step.title
        return defaults

    def process(self):
        _debug.pipeline("propose_change", wizards=self)
        for wizard in self:
            _debug.logic(
                "propose_change_routed",
                wizard=wizard.id,
                change_type=wizard.change_type,
                workorder=wizard.workorder_id.id,
            )
            if wizard.change_type == "update_step":
                wizard._update_step()
            elif wizard.change_type == "remove_step":
                wizard._remove_step()
            elif wizard.change_type == "set_picture":
                wizard._update_picture()

    def _get_workorder_name(self):
        if self.workorder_id.employee_id:
            return self.workorder_id.employee_id.name
        return self.env.user.name

    def _get_update_step_note(self, original_title=False):
        tl_text = self.env._(
            "New Instruction suggested by %(user_name)s",
            user_name=self._get_workorder_name(),
        )
        body = Markup("<b>%s</b>") % tl_text
        if self.note and not is_html_empty(self.note):
            body += Markup("<br/><b>%s</b>%s") % (self.env._("Instruction:"), self.note)
        if self.comment:
            body += Markup("<br/><b>%s</b> %s") % (self.env._("Reason:"), self.comment)
        if self.title and self.title != original_title:
            body += Markup("<br/><b>%s %s</b>") % (
                self.env._("New Title suggested:"),
                self.title,
            )
        return body

    def _update_step(self, notify_bom=True) -> None:
        self.check_singleton()
        existing_imgs = []
        is_blank = is_html_empty(self.note)
        if not is_html_empty(self.step_id.note) and (
            is_blank or re.sub(self.IMG_REGEX, "", self.note) == self.note
        ):
            # blank suggestion or only text => keep existing images if they exist
            existing_imgs = re.findall(self.IMG_REGEX, self.step_id.note)
        if existing_imgs:
            self.step_id.note = Markup("<p>%s</p>") % Markup("<br>").join(
                map(Markup, existing_imgs)
            )
            if not is_blank:
                self.step_id.note = self.note + self.step_id.note
        else:
            self.step_id.note = self.note
        if notify_bom and self.workorder_id.production_id.bom_id:
            body = self.env._(
                "BoM feedback %(step)s (%(production)s - %(operation)s)",
                step=self.step_id.title,
                production=self.workorder_id.production_id.name,
                operation=self.workorder_id.operation_id.name,
            )
            body += Markup("<br/>%s") % self._get_update_step_note(self.step_id.title)
            self.workorder_id.production_id.bom_id.message_post(body=body)
        if self.title and self.title != self.step_id.title:
            _debug.lifecycle(
                "step_title_changed",
                step=self.step_id.id,
                workorder=self.workorder_id.id,
            )
            self.step_id.title = self.title

    def _get_remove_step_note(self):
        tl_text = self.env._(
            "%(user_name)s suggests to delete this instruction",
            user_name=self._get_workorder_name(),
        )
        body = Markup("<b>%s</b>") % tl_text
        if self.comment:
            body += Markup("<br/><b>%s</b> %s") % (self.env._("Reason:"), self.comment)
        return body

    def _remove_step(self, notify_bom=True) -> None:
        self.check_singleton()
        if not self.step_id.point_id and not (
            self.step_id.test_type.startswith("register_")
        ):
            # remove additionmal step
            _debug.lifecycle(
                "step_removed", step=self.step_id.id, workorder=self.workorder_id.id
            )
            self.step_id.workorder_id._update_current_quality_check("next")
            self.step_id.unlink()
        bom = self.step_id.workorder_id.production_id.bom_id
        if notify_bom and bom:
            body = self.env._(
                "BoM feedback %(step)s (%(production)s - %(operation)s)",
                step=self.step_id.title,
                production=self.workorder_id.production_id.name,
                operation=self.workorder_id.operation_id.name,
            )
            body += Markup("<br/>%s") % self._get_remove_step_note()
            bom.message_post(body=body)

    @api.model
    def image_url(self, record, field) -> str:
        """Returns a local url that points to the image field of a given browse record."""
        return "/web/image/%s/%s/%s" % (record._name, record.id, field)

    def _get_set_picture_note(self):
        lt_text = self.env._(
            "%(user_name)s suggests to use this document as instruction",
            user_name=self._get_workorder_name(),
        )
        return Markup(
            '<b>%s</b><br/><img style="max-width: 75%%" class="img-fluid" src="%s"/>'
        ) % (lt_text, self.image_url(self, "picture"))

    def _update_picture(self, notify_bom=True) -> None:
        self.check_singleton()
        # remove html existing images, but keep existing text
        existing_text = False
        if not is_html_empty(self.step_id.note):
            existing_text = Markup(re.sub(self.IMG_REGEX, "", self.step_id.note))
        if existing_text and not is_html_empty(existing_text):
            self.step_id.note = existing_text
        self.step_id.worksheet_document = self.picture
        bom = self.step_id.workorder_id.production_id.bom_id
        if notify_bom and bom:
            body = self.env._(
                "BoM feedback %(step)s (%(production)s - %(operation)s)",
                step=self.step_id.title,
                production=self.workorder_id.production_id.name,
                operation=self.workorder_id.operation_id.name,
            )
            body += Markup("<br/>%s") % self._get_set_picture_note()
            bom.message_post(body=body)
