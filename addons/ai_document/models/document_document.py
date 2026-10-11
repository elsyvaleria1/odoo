import ast
import datetime
import logging
from collections.abc import Iterable

import lxml.html
from markupsafe import Markup

from odoo import api, fields, models
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import is_html_empty

from odoo.addons.ai_fields.tools import ai_field_insert, parse_ai_prompt_values

_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    _ai_rec_name = "name"

    AI_DOCUMENTS_CRON_BATCH_SIZE = 10

    ai_sortable = fields.Boolean(
        string="AI Sortable",
        compute="_compute_ai_sortable",
        search="_search_ai_sortable",
    )
    ai_sort_prompt = fields.Html(
        string="AI Folder Sort Prompt",
        sanitize=True,
        sanitize_output_method="xml",
        groups="base.group_system",
        help="Prompt used to automatically sort files moved in this folder",
    )
    ai_to_sort = fields.Boolean(
        string="AI To Sort",
        help="Flag to mark the files as to be sorted with AI",
    )

    _check_ai_sort_prompt = models.Constraint(
        "CHECK(COALESCE(ai_sort_prompt, '') = '' OR (type = 'folder' AND shortcut_document_id IS NULL))",
        "Only folders can be auto-sorted.",
    )

    def write(self, vals):
        if "folder_id" in vals:
            _debug.logic("ai_sort_flag_cleared", reason="manual_move", documents=self)
            vals["ai_to_sort"] = False
        return super().write(vals)

    @api.depends("shortcut_document_id", "type", "attachment_id")
    def _compute_ai_sortable(self) -> None:
        for document in self:
            document.ai_sortable = (
                not document.shortcut_document_id
                and document.type == "binary"
                and document.attachment_id
            )

    def _search_ai_sortable(self, operator, value):
        if (
            operator != "in"
            or not isinstance(value, Iterable)
            or tuple(value) != (True,)
        ):
            return NotImplemented

        return [
            ("shortcut_document_id", "=", False),
            ("type", "=", "binary"),
            ("attachment_id", "!=", False),
        ]

    def _pdf_split(
        self, new_files=(), open_files=(), first_source_ids=(), user_folder=None
    ):
        return super(
            DocumentsDocument, self.with_context(ai_documents_skip_autosort=True)
        )._pdf_split(new_files, open_files, first_source_ids, user_folder)

    def _ai_action_move_in_folder(self, folder_id) -> str:
        self.check_singleton()
        folder_sudo = self.browse(folder_id).sudo()
        if folder_sudo.type != "folder":
            _debug.logic("ai_move_refused", reason="not_a_folder", target=folder_id)
            raise UserError(self.env._("Cannot move in a non-folder."))

        if not self.ai_sortable:
            _debug.logic("ai_move_refused", reason="not_sortable", document=self)
            raise UserError(self.env._("This document cannot be auto-sorted."))

        if folder_sudo == self.folder_id:
            _debug.logic("ai_move_noop", reason="already_there", document=self)
            return self.env._(
                'Moved to "%(folder)s".', folder=self._ai_truncate(folder_sudo.name)
            )

        original_folder = self.folder_id
        if (action := self.env.context.get("ai_executed_action")) and isinstance(
            action, models.BaseModel
        ):
            original_folder = action.ai_autosort_folder_id

        _prompt, _fields, allowed_ids = parse_ai_prompt_values(
            self.env,
            original_folder.sudo().ai_sort_prompt,
            "document.document",
            False,
        )
        if folder_sudo.id not in allowed_ids:
            _debug.logic(
                "ai_move_refused",
                reason="target_not_in_prompt",
                document=self,
                target=folder_id,
            )
            raise UserError(
                self.env._(
                    "This folder isn't specified in the prompt and cannot be used as target."
                )
            )

        _debug.lifecycle(
            "ai_moved", document=self, target=folder_sudo, source=original_folder
        )
        self.sudo().folder_id = folder_sudo.id
        return self.env._(
            'Moved to "%(folder)s".', folder=self._ai_truncate(folder_sudo.name)
        )

    def _ai_action_add_tags(self, tag_names) -> str:
        self.check_singleton()
        tags = self.env["document.tag"].search([("name", "in", tag_names)])
        if not tags:
            _debug.logic("ai_tags_refused", reason="unknown", document=self)
            raise UserError(self.env._("Tags not found: %s", tag_names))

        _debug.lifecycle("ai_tags_added", document=self, tags=tags)
        self.tag_ids |= tags
        return self.env._("Tag(s) %s added", ", ".join(tags.mapped("name")))

    @api.model
    def _get_domain_base_server_actions(self):
        return (
            super()._get_domain_base_server_actions()
            & Domain("ai_autosort_folder_id", "=", False)
            & (Domain("ai_tool_schema", "=", False) | Domain("use_in_ai", "=", False))
        )

    @api.model
    def _get_fields_search_panel(self):
        panel_fields = super()._get_fields_search_panel()
        if self.env.user.has_group("base.group_system"):
            panel_fields.append("ai_sort_prompt")
        return panel_fields

    @api.model
    def search_panel_select_range(self, field_name, **kwargs):
        res = super().search_panel_select_range(field_name, **kwargs)
        if field_name == "user_folder_id":
            folders_ids = [
                vals["id"] for vals in res["values"] if isinstance(vals["id"], int)
            ]
            folders_with_sort_prompts_ids = set(
                self.sudo()
                .search([("id", "in", folders_ids), ("ai_sort_prompt", "!=", False)])
                .ids
            )
            for vals in res["values"]:
                vals["ai_has_sort_prompt"] = vals["id"] in folders_with_sort_prompts_ids
        return res


    def _message_post_after_hook_template_values(self):
        return {
            **super()._message_post_after_hook_template_values(),
            "ai_to_sort": self.ai_to_sort,
        }

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        if custom_values and (folder_id := custom_values.get("folder_id")):
            rule = (
                self.env["automation.rule"]
                .sudo()
                .search([("ai_autosort_folder_id", "=", folder_id)])
            )
            if rule:
                cron = self.env.ref(
                    "ai_document.ir_cron_ai_documents_sort",
                    raise_if_not_found=False,
                )
                if cron:
                    _debug.pipeline(
                        "ai_sort_deferred",
                        by="mail_alias",
                        folder=folder_id,
                        at=self.env.cr.now(),
                    )
                    _logger.info("AI Documents: scheduling auto-sorting")
                    custom_values["ai_to_sort"] = True
                    cron._trigger(self.env.cr.now() + datetime.timedelta(minutes=1))
                else:
                    _logger.warning("AI Documents: AI sorting CRON not found")

        return super(
            DocumentsDocument, self.with_context(ai_documents_skip_autosort=True)
        ).message_new(msg_dict, custom_values)

    @api.model
    def _cron_ai_sort(self) -> None:
        cron = self.env.ref(
            "ai_document.ir_cron_ai_documents_sort",
            raise_if_not_found=False,
        )
        if cron:
            to_sort_count = self.search_count([("ai_to_sort", "=", True)])
            cron._commit_progress(remaining=to_sort_count)
            if not to_sort_count:
                return

        to_sort = self.search(
            [("ai_to_sort", "=", True)],
            order="create_date ASC, id ASC",
            limit=self.AI_DOCUMENTS_CRON_BATCH_SIZE,
        )

        rules = (
            self.env["automation.rule"]
            .sudo()
            .search([("ai_autosort_folder_id", "in", to_sort.folder_id.ids)])
        )
        rules = rules.grouped("ai_autosort_folder_id")
        _debug.pipeline("ai_sort_pass", documents=to_sort, rules=len(rules))

        for document in to_sort:
            document.ai_to_sort = False
            if cron:
                cron._commit_progress(1)
            if not document.ai_sortable:
                _debug.logic(
                    "ai_sort_skipped", reason="not_sortable", document=document
                )
                continue

            rule = rules.get(document.folder_id)
            if not rule:
                _debug.logic("ai_sort_skipped", reason="no_rule", document=document)
                continue
            try:
                with (
                    _debug.perf("ai_sort_rule", cr=self.env.cr, document=document),
                    self.env.cr.savepoint(),
                ):
                    rule._process(
                        document,
                        rule.filter_domain and ast.literal_eval(rule.filter_domain),
                    )
            except PG_RETRY_EXCEPTIONS:
                self.env.cr.rollback()
                document.ai_to_sort = True
                _debug.logic("ai_sort_requeued", document=document)
            except Exception:
                _debug.logic("ai_sort_failed", document=document)
                _logger.exception("AI Documents: sorting of %s failed", document.id)

        return


    def action_ai_sort(self) -> dict | None:
        documents = self.filtered(
            lambda d: d.ai_sortable and d.folder_id.sudo().ai_sort_prompt
        )
        if not documents:
            _debug.logic("ai_sort_refused", reason="none_suitable", documents=self)
            raise UserError(self.env._("No document suitable for AI sorting."))

        _debug.pipeline("ai_sort_manual", documents=documents)
        if len(documents) > 50:
            cron = self.env.ref(
                "ai_document.ir_cron_ai_documents_sort",
                raise_if_not_found=False,
            )
            if cron:
                _debug.pipeline(
                    "ai_sort_deferred",
                    by="batch_size",
                    documents=documents,
                    at=self.env.cr.now(),
                )
                _logger.info("AI Documents: scheduling auto-sorting")
                documents.ai_to_sort = True
                cron._trigger(self.env.cr.now() + datetime.timedelta(minutes=1))
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "type": "success",
                        "message": self.env._("Auto sorting has been scheduled"),
                        "sticky": False,
                    },
                }
        ai_actions = (
            self.env["ir.actions.server"]
            .sudo()
            .search([("ai_autosort_folder_id", "in", documents.folder_id.ids)])
        )
        ai_action_per_folder = ai_actions.grouped("ai_autosort_folder_id")

        for document in documents:
            ai_action = ai_action_per_folder.get(document.folder_id)
            if not ai_action:
                _debug.logic("ai_sort_skipped", reason="no_action", document=document)
                continue

            document.ai_to_sort = False
            ai_action._ai_action_run(document)

        return None

    def _ai_setup_sort_actions(self, ai_tool_ids=()) -> None:
        self.check_singleton()

        content = lxml.html.fromstring(f"<div>{self.ai_sort_prompt or ''}</div>")
        for el in content.xpath("//*[@data-ai-record-id]"):
            el.drop_tree()
        is_prompt_empty = is_html_empty(lxml.html.tostring(content).decode())

        automation_rule = self.env["automation.rule"].search(
            [("ai_autosort_folder_id", "=", self.id)],
            limit=1,
        )
        ir_action = self.env["ir.actions.server"].search(
            [("ai_autosort_folder_id", "=", self.id)],
            limit=1,
        )

        if is_prompt_empty:
            automation_rule.unlink()
            ir_action.unlink()
            return

        ir_actions_tools = self.env["ir.actions.server"].browse(ai_tool_ids)
        ir_actions_tools.use_in_ai = True

        action_values = {
            "name": self.env._("Auto-sort documents in %s", self.name),
            "ai_autosort_folder_id": self.id,
            "ai_tool_ids": ir_actions_tools.ids or False,
            "model_id": self.env.ref("document.model_document_document").id,
            "state": "ai",
            "ai_action_prompt": Markup("""
                <p>
                    %s
                </p>
                <br/>
            """)
            % self.env._(
                """Here is a document called %(document_name)s and whose content is %(content)s and tags are %(tags)s. The mimetype of the document is %(mimetype)s.""",
                document_name=ai_field_insert("name", self.env._("Name")),
                content=ai_field_insert(
                    "attachment_id", self.env._("Document Content")
                ),
                tags=ai_field_insert("tag_ids.name", self.env._("Tags > Name")),
                mimetype=ai_field_insert("mimetype", self.env._("Mimetype")),
            ),
        }
        if ir_action:
            ir_action.write(action_values)
        else:
            ir_action = self.env["ir.actions.server"].create(action_values)

        automation_values = {
            "name": self.env._("Auto-sort documents in %s", self.name),
            "ai_autosort_folder_id": self.id,
            "filter_domain": repr(
                [("folder_id", "=", self.id), ("ai_sortable", "=", True)]
            ),
            "model_id": self.env.ref("document.model_document_document").id,
            "trigger": "on_create_or_write",
            "trigger_field_ids": self.env.ref(
                "document.field_document_document__folder_id"
            ).ids,
            "action_server_ids": ir_action.ids,
        }
        if automation_rule:
            automation_rule.write(automation_values)
        else:
            self.env["automation.rule"].create(automation_values)

    def _ai_folder_insert(self, folder_id):
        return Markup('<span data-ai-record-id="%i"/>') % folder_id

    def _ai_format_records(self) -> dict:
        ancestors = self.env["document.document"].browse(
            self._get_ancestor_ids(include_self=True)
        )
        ancestors_names = {
            a.id: self._ai_truncate(a.name).replace(">", "-") for a in ancestors
        }

        return {
            folder.id: {
                "name": self._ai_truncate(folder.name),
                "path": " > ".join(
                    ancestors_names[i]
                    for i in folder._get_ancestor_ids(include_self=True)
                ),
                "company": folder.company_id.name,
                "owner_user": {"id": folder.owner_id.id, "name": folder.owner_id.name},
            }
            for folder in self
        }
