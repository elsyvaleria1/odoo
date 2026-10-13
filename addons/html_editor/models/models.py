import binascii
import re

from odoo import api, models
from odoo.tools import clean_context

_DATA_URI_IMAGE = re.compile(
    r'(<img\b[^>]*?\ssrc=)([\'"])data:image/[a-z]+?;base64,([a-z0-9+/\n]{3,}=*)\n*\2'
    r'(?: data-filename="([^"]*)")?',
    re.IGNORECASE,
)


def _names_with_data_uri(vals) -> set[str]:
    return {
        name
        for name, value in vals.items()
        if isinstance(value, str) and "data:image" in value
    }


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def _get_view_field_attributes(self):
        keys = super()._get_view_field_attributes()
        keys.append("sanitize")
        keys.append("sanitize_tags")
        return keys

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if names := records._html_inline_image_fields(
            {name for vals in vals_list for name in _names_with_data_uri(vals)}
        ):
            records._html_extract_data_images(names)
        return records

    def write(self, vals):
        res = super().write(vals)
        if names := self._html_inline_image_fields(_names_with_data_uri(vals)):
            self._html_extract_data_images(names)
        return res

    def _html_inline_image_fields(self, names: set[str]) -> list[str]:
        if self._transient:
            return []
        return [
            name
            for name in names
            if (field := self._fields.get(name))
            and field.type == "html"
            and field.store
            and not field.related
        ]

    def _html_extract_data_images(self, field_names) -> None:
        Attachments = self.env["ir.attachment"].with_context(
            clean_context(self.env.context)
        )
        for record in self:
            updates = {}
            for name in field_names:
                html = record[name]
                if not html or "data:image" not in html:
                    continue
                created = {}

                def to_attachment(match, record=record, created=created):
                    src, quote, payload = match.group(1, 2, 3)
                    if payload not in created:
                        filename = match.group(4) or f"image{len(created)}"
                        try:
                            attachment = Attachments.create(
                                {
                                    "name": filename,
                                    "datas": payload,
                                    "res_model": record._name,
                                    "res_id": record.id,
                                }
                            )
                        except binascii.Error:
                            return f"{src}{quote}{quote}"
                        attachment.generate_access_token()
                        token = attachment.access_token
                        created[payload] = (
                            f"/web/image/{attachment.id}?access_token={token}",
                            filename,
                            attachment.id,
                        )
                    url, filename, attachment_id = created[payload]
                    return (
                        f'{src}{quote}{url}{quote} alt="{filename}" '
                        f'data-attachment-id="{attachment_id}"'
                    )

                rewritten = _DATA_URI_IMAGE.sub(to_attachment, html)
                if rewritten != html:
                    updates[name] = rewritten
            if updates:
                super(Base, record).write(updates)
