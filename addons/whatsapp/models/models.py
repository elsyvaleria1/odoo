from odoo import api, models

from odoo.addons.whatsapp.models.whatsapp_template import (
    COMMON_WHATSAPP_PHONE_SAFE_FIELDS,
)
from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation


class Base(models.AbstractModel):
    _inherit = "base"

    def _whatsapp_phone_resolve(self, fpath) -> tuple:
        self.check_singleton()
        if not fpath:
            return False, None
        phone_record_path, phone_record_field = (
            fpath.rsplit(".", 1) if "." in fpath else ("", fpath)
        )
        phone_record = self.mapped(phone_record_path) if phone_record_path else self
        field = phone_record._fields.get(phone_record_field)
        if field is None:
            return False, None
        if field.type == "many2many" and field.comodel_name == "phone.number":
            phone = phone_record.mapped(phone_record_field)._primary(
                "whatsapp", "mobile"
            )
            return phone.number or False, phone.country_id or None
        value = next(iter(phone_record.mapped(phone_record_field)), None)
        if isinstance(value, models.BaseModel):
            value = value.display_name if value else ""
        return value or False, None

    @api.model
    def _whatsapp_phone_format(
        self, fpath=None, number=None, raise_on_format_error=False
    ):
        self.check_singleton()
        if fpath:
            number, phone_record_country = self._whatsapp_phone_resolve(fpath)
            if not phone_record_country:
                phone_record_path = fpath.rsplit(".", 1)[0] if "." in fpath else ""
                phone_record = (
                    self.mapped(phone_record_path) if phone_record_path else self
                )
                country_field = phone_record._phone_get_country_field()
                phone_record_country = (
                    phone_record.mapped(country_field)[:1] if country_field else None
                )
        else:
            phone_record_country = None

        return wa_phone_validation.wa_phone_format(
            self,
            country=phone_record_country or self._phone_get_country().get(self.id),
            number=number or "",
            force_format="WHATSAPP",
            raise_exception=raise_on_format_error,
        )

    def _whatsapp_get_portal_url(self):
        if self._name in {
            "sale.order",
            "account.move",
            "project.project",
            "project.task",
            "purchase.order",
            "helpdesk.ticket",
        } and hasattr(self, "get_portal_url"):
            self.check_singleton()
            return self.get_portal_url()
        contactus_page = self.env.ref(
            "website.contactus_page", raise_if_not_found=False
        )
        return contactus_page.url if contactus_page else False

    def _whatsapp_get_responsible(
        self, related_message=False, related_record=False, whatsapp_account=False
    ):

        self.check_singleton()
        responsible_users = self.env["res.users"]

        def filter_suitable_users(user):
            return user.active and user._is_internal() and not user._is_superuser()

        for field in ["user_id", "user_ids"]:
            if field in self._fields and self[field]:
                responsible_users = self[field].filtered(filter_suitable_users)

        if related_message:
            responsible_users |= related_message.author_id.user_ids.filtered(
                filter_suitable_users
            )

        if responsible_users:
            return responsible_users

        if related_message and not related_record:
            related_record = self.env[related_message.model].browse(
                related_message.res_id
            )

        if related_record:
            responsible_users = related_record.create_uid.filtered(
                filter_suitable_users
            )

            if not responsible_users:
                responsible_users = related_record.write_uid.filtered(
                    filter_suitable_users
                )

        if not responsible_users:
            if not whatsapp_account:
                whatsapp_account = self.env["whatsapp.account"].search([], limit=1)

            responsible_users = whatsapp_account.notify_user_ids

        return responsible_users

    def _wa_get_safe_phone_fields(self):
        return list(COMMON_WHATSAPP_PHONE_SAFE_FIELDS)
