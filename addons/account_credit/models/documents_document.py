from urllib.parse import quote

from odoo import fields, models


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    amount = fields.Float(
        help="Amount for promissory notes, guarantees, contracts, etc."
    )
    collateral_amount = fields.Float(help="Collateral amount for guarantees")
    is_guarantor = fields.Boolean(help="Indicates if this document acts as a guarantee")
    has_amount = fields.Boolean(related="document_type_id.has_amount")
    has_collateral = fields.Boolean(related="document_type_id.has_collateral")
    has_guarantor = fields.Boolean(related="document_type_id.has_guarantor")

    def write(self, vals):
        """Keep the derived credit file in step with a document that moves.

        ``res.partner.credit_document_ids`` is a One2many whose domain is the
        subtree of the company's credit folder. The ORM keeps a One2many in
        step through its inverse only -- a partner's cache is updated when a
        document writes ``partner_id`` -- so a document changing ``folder_id``
        walks in or out of the file without anything telling the partner.
        What is cached stays cached, and ``credit_limit`` and
        ``credit_document_compliant``, both stored, then recompute from that
        stale cache even though ``@api.depends`` did mark them.

        So the cache is dropped here and the partners are told. The domain is
        not part of the dependency graph, but ``folder_id`` is a write we see.
        """
        if "folder_id" not in vals:
            return super().write(vals)
        partners = self._get_credit_file_partners()
        result = super().write(vals)
        partners |= self._get_credit_file_partners()
        if partners:
            partners.invalidate_recordset(["credit_document_ids"])
            partners.modified(["credit_document_ids"])
        return result

    def _get_credit_file_partners(self):
        """The partners whose credit file the records in ``self`` belong to.

        A folder stands for everything under it: moving one carries its whole
        subtree in or out of the credit tree at once, and the framework's own
        traversal would reach the folder's own contact and nothing else.
        """
        documents = self.filtered(lambda document: document.type != "folder")
        partners = documents.partner_id
        for folder in self - documents:
            partners |= (
                self.sudo()
                .search(
                    [
                        ("folder_id", "child_of", folder.id),
                        ("partner_id", "!=", False),
                        ("type", "!=", "folder"),
                    ]
                )
                .partner_id
            )
        return partners

    def _get_compliance_issues(self):
        self.check_singleton()
        issues = []
        doc_type = self.document_type_id
        if not doc_type:
            return issues
        if doc_type.has_expiration and self.expiration_state == "expired":
            issues.append(self.env._("Expired"))
        if doc_type.has_amount and not self.amount:
            issues.append(self.env._("Missing amount"))
        if doc_type.has_collateral and not self.collateral_amount:
            issues.append(self.env._("Missing collateral amount"))
        return issues

    def action_view_document(self):
        self.check_singleton()
        return {
            "type": "ir.actions.act_url",
            "url": (
                f"/documents/content/{quote(self.access_token, safe='')}?download=false"
            ),
            "target": "new",
        }
