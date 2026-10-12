import typing
from collections.abc import Callable, Mapping, Sequence

from odoo import api, fields, models, tools
from odoo.libs.debug_log import DebugLog

from .mixin_mail_render import BYPASS_RESTRICTED_RENDERING, RenderResId

if typing.TYPE_CHECKING:
    from .mail_template import MailTemplate

_debug = DebugLog(__name__)


class MixinMailComposer(models.AbstractModel):
    _name = "mixin.mail.composer"
    _inherit = ["mixin.mail.render"]
    _description = "Mail Composer Mixin"

    _template_field_counterparts = {"body": "body_html"}

    subject = fields.Char(
        compute="_compute_subject",
        compute_sudo=False,
        store=True,
        readonly=False,
    )
    body = fields.Html(
        string="Contents",
        sanitize="email_outgoing",
        compute="_compute_body",
        compute_sudo=False,
        store=True,
        readonly=False,
        render_engine="qweb",
        render_options={"post_process": True},
    )
    body_has_template_value = fields.Boolean(
        string="Body content is the same as the template",
        compute="_compute_body_has_template_value",
    )
    template_id: MailTemplate = fields.Many2one(
        comodel_name="mail.template",
        string="Mail Template",
        domain="[('model', '=', render_model)]",
    )
    lang = fields.Char(
        compute="_compute_lang",
        precompute=True,
        compute_sudo=False,
        store=True,
        readonly=False,
    )
    is_mail_template_editor = fields.Boolean(
        string="Is Editor",
        compute="_compute_is_mail_template_editor",
    )
    can_edit_body = fields.Boolean(compute="_compute_can_edit_body")

    def _copy_from_template(
        self, field_name: str, is_empty: Callable[[typing.Any], bool] | None = None
    ) -> None:
        template_field = self._get_template_field(field_name)
        for record in self:
            if not record.template_id:
                record[field_name] = False
                continue
            value = record.template_id[template_field]
            if not (is_empty(value) if is_empty else not value):
                record[field_name] = value

    @api.depends("template_id")
    def _compute_subject(self) -> None:
        self._copy_from_template("subject")

    @api.depends("template_id")
    def _compute_body(self) -> None:
        self._copy_from_template("body", is_empty=tools.is_html_empty)

    @api.depends("template_id")
    def _compute_lang(self) -> None:
        self._copy_from_template("lang")

    @api.depends("body", "template_id")
    def _compute_body_has_template_value(self) -> None:
        for composer_mixin in self:
            template_body = composer_mixin.template_id.body_html
            if template_body:
                template_body = composer_mixin._fields["body"].convert_to_cache(
                    template_body, composer_mixin
                )
            composer_mixin.body_has_template_value = bool(
                composer_mixin.template_id
                and not tools.is_html_empty(composer_mixin.body)
                and composer_mixin.body == template_body
            )

    @api.depends_context("uid")
    def _compute_is_mail_template_editor(self) -> None:
        is_mail_template_editor = self.env.is_admin() or self.env.user.has_group(
            "mail.group_mail_template_editor"
        )
        for record in self:
            record.is_mail_template_editor = is_mail_template_editor

    @api.depends("template_id", "is_mail_template_editor")
    def _compute_can_edit_body(self) -> None:
        for record in self:
            record.can_edit_body = (
                record.is_mail_template_editor or not record.template_id
            )

    def _get_template_field(self, field_name: str) -> str:
        if field_name not in self._fields:
            raise ValueError(f"{self._name} has no field {field_name!r} to render")
        template_field = self._template_field_counterparts.get(field_name, field_name)
        if template_field not in self.env["mail.template"]._fields:
            raise ValueError(
                f"{self._name}.{field_name} has no counterpart on mail.template"
            )
        return template_field

    def _is_value_from_template(self, field_name: str) -> bool:
        self.check_singleton()
        if not self.template_id:
            return False
        if field_name == "body":
            return self.body_has_template_value
        value = self[field_name]
        template_value = self.template_id[self._get_template_field(field_name)]
        return value == template_value or not (value or template_value)

    def _is_template_value_render_required(self, field_name: str) -> bool:
        self.check_singleton()
        return (
            field_name == "body"
            and not self.is_mail_template_editor
            and not self.can_edit_body
        )

    def _render_lang(
        self, res_ids: Sequence[RenderResId], engine: str = "inline_template"
    ) -> Mapping[RenderResId, str | typing.Literal[False]]:
        self.check_singleton()
        record = self
        if self._is_value_from_template("lang") and not self.is_mail_template_editor:
            record = self.with_context(
                bypass_restricted_rendering=BYPASS_RESTRICTED_RENDERING
            )
        return super(MixinMailComposer, record)._render_lang(res_ids, engine=engine)

    def _render_field(
        self,
        field_name: str,
        res_ids: Sequence[RenderResId],
        engine: str = "inline_template",
        compute_lang: bool = False,
        res_ids_lang: Mapping[RenderResId, str | typing.Literal[False]]
        | typing.Literal[False] = False,
        set_lang: str | typing.Literal[False] = False,
        add_context: dict[str, typing.Any] | None = None,
        options: dict[str, typing.Any] | None = None,
    ) -> dict[RenderResId, str]:
        self.check_singleton()
        if not self.template_id:
            self._check_render_authoring(
                self[field_name],
                getattr(self._fields[field_name], "render_engine", None) or engine,
                self.render_model,
            )
            return super()._render_field(
                field_name,
                res_ids,
                engine=engine,
                compute_lang=compute_lang,
                res_ids_lang=res_ids_lang,
                set_lang=set_lang,
                add_context=add_context,
                options=options,
            )

        template_field = self._get_template_field(field_name)
        from_template = self._is_value_from_template(field_name)
        translation_asked = bool(compute_lang or set_lang)

        if self._is_template_value_render_required(field_name) or (
            translation_asked and from_template
        ):
            _debug.logic(
                "composer_field_render",
                model=self._name,
                record=self.id,
                field=field_name,
                by="template",
                template=self.template_id.id,
                translation=translation_asked,
            )
            if translation_asked and not res_ids_lang and not set_lang:
                res_ids_lang = self._get_res_ids_lang(res_ids)
            return self.template_id._render_field(
                template_field,
                res_ids,
                engine=engine,
                compute_lang=compute_lang,
                res_ids_lang=res_ids_lang,
                set_lang=set_lang,
                add_context=add_context,
                options=options,
            )

        record = self
        if from_template and not self.is_mail_template_editor:
            record = self.with_context(
                bypass_restricted_rendering=BYPASS_RESTRICTED_RENDERING
            )
        elif not from_template:
            self._check_render_authoring(
                self[field_name],
                getattr(self._fields[field_name], "render_engine", None) or engine,
                self.render_model,
                self.template_id,
            )
        _debug.logic(
            "composer_field_render",
            model=self._name,
            record=self.id,
            field=field_name,
            by="composer",
            bypass=from_template and not self.is_mail_template_editor,
        )
        return super(MixinMailComposer, record)._render_field(
            field_name,
            res_ids,
            engine=engine,
            compute_lang=compute_lang,
            res_ids_lang=res_ids_lang,
            set_lang=set_lang,
            add_context=add_context,
            options=options,
        )
