import base64
import logging
from datetime import datetime

import vobject

from odoo.fields import Command

_logger = logging.getLogger(__name__)

TEL_TYPE_PARAMS = {
    "mobile": ["CELL", "VOICE"],
    "landline": ["WORK", "VOICE"],
    "fax": ["WORK", "FAX"],
    "whatsapp": ["CELL", "VOICE"],
    "emergency": ["VOICE"],
}


class VCardBuilder:
    def partner_to_vcard(self, partner, env=None):
        vcard = vobject.vCard()

        vcard.add("version")
        vcard.version.value = "4.0"

        vcard.add("uid")
        vcard.uid.value = partner.vcard_uid or f"contact-{partner.id}@odoo"

        vcard.add("fn")
        vcard.fn.value = partner.display_name or partner.name or "Unknown"

        vcard.add("n")
        if hasattr(partner, "lastname") and hasattr(partner, "firstname"):
            vcard.n.value = vobject.vcard.Name(
                family=partner.lastname or "",
                given=partner.firstname or "",
            )
        else:
            name_parts = (partner.name or "").split(" ", 1)
            vcard.n.value = vobject.vcard.Name(
                family=(
                    name_parts[-1]
                    if len(name_parts) > 1
                    else name_parts[0]
                    if name_parts
                    else ""
                ),
                given=name_parts[0] if len(name_parts) > 1 else "",
            )

        if hasattr(partner, "ref") and partner.ref:
            nickname = vcard.add("nickname")
            nickname.value = partner.ref

        if partner.email:
            email = vcard.add("email")
            email.value = partner.email
            email.type_param = ["WORK", "INTERNET"]
            if hasattr(partner, "email_pref") and partner.email_pref:
                email.params["PREF"] = ["1"]

        if hasattr(partner, "email_ids"):
            for idx, email_rec in enumerate(partner.email_ids[:3]):
                email = vcard.add("email")
                email.value = email_rec.email
                email.type_param = ["INTERNET"]
                if idx == 0 and not partner.email:
                    email.params["PREF"] = ["1"]

        for phone in partner.phone_ids:
            tel = vcard.add("tel")
            tel.value = self._format_phone(phone.number)
            tel.type_param = TEL_TYPE_PARAMS.get(phone.type, ["WORK", "VOICE"])
            if phone.primary:
                tel.params["PREF"] = ["1"]

        if any(
            [
                partner.street,
                partner.street2,
                partner.city,
                partner.state_id,
                partner.zip,
                partner.country_id,
            ]
        ):
            adr = vcard.add("adr")
            street_parts = [p for p in [partner.street, partner.street2] if p]
            adr.value = vobject.vcard.Address(
                street="\n".join(street_parts),
                city=partner.city or "",
                region=partner.state_id.name if partner.state_id else "",
                code=partner.zip or "",
                country=partner.country_id.name if partner.country_id else "",
            )
            adr.type_param = ["WORK"]

        if partner.parent_id or (partner.is_company and partner.name):
            org = vcard.add("org")
            if partner.is_company:
                org.value = [partner.name]
            elif partner.parent_id:
                org.value = [partner.parent_id.name]

        if partner.function:
            title = vcard.add("title")
            title.value = partner.function

        if hasattr(partner, "role") and partner.role:
            role = vcard.add("role")
            role.value = partner.role

        if partner.website:
            url = vcard.add("url")
            url.value = partner.website
            url.type_param = ["WORK"]

        if partner.image_128:
            try:
                photo = vcard.add("photo")
                image_data = partner.image_128
                if isinstance(image_data, bytes):
                    b64_str = base64.b64encode(image_data).decode("ascii")
                else:
                    b64_str = image_data
                photo.value = f"data:image/png;base64,{b64_str}"
            except (TypeError, ValueError) as e:
                _logger.warning(
                    "Failed to encode photo for partner %s: %s", partner.id, e
                )

        if hasattr(partner, "tag_ids") and partner.tag_ids:
            categories = vcard.add("categories")
            categories.value = [cat.name for cat in partner.tag_ids]

        if partner.comment:
            note = vcard.add("note")
            note.value = partner.comment

        if hasattr(partner, "birthdate") and partner.birthdate:
            bday = vcard.add("bday")
            bday.value = partner.birthdate.strftime("%Y%m%d")

        x_odoo_id = vcard.add("x-odoo-id")
        x_odoo_id.value = str(partner.id)

        x_type = vcard.add("x-odoo-type")
        x_type.value = "company" if partner.is_company else "individual"

        if partner.write_date:
            rev = vcard.add("rev")
            rev.value = partner.write_date.strftime("%Y%m%dT%H%M%SZ")

        prodid = vcard.add("prodid")
        prodid.value = "-//Odoo//DAV Sync//EN"

        return vcard.serialize()

    def _format_phone(self, phone):
        if not phone:
            return ""
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        return cleaned or phone

    def vcard_to_partner_vals(self, vcard_data, env=None):
        try:
            vcard = vobject.readOne(vcard_data)
        except Exception as e:
            _logger.error("Failed to parse vCard: %s", e)
            raise ValueError(f"Invalid vCard data: {e}") from e

        vals = {}

        if hasattr(vcard, "uid"):
            vals["vcard_uid"] = vcard.uid.value

        if hasattr(vcard, "fn"):
            vals["name"] = vcard.fn.value

        if hasattr(vcard, "n"):
            name_parts = vcard.n.value
            if hasattr(name_parts, "given") and hasattr(name_parts, "family"):
                if name_parts.given and name_parts.family:
                    vals["name"] = f"{name_parts.given} {name_parts.family}".strip()
                elif name_parts.given:
                    vals["name"] = name_parts.given
                elif name_parts.family:
                    vals["name"] = name_parts.family

        if hasattr(vcard, "email"):
            vals["email"] = vcard.email.value
        elif hasattr(vcard, "email_list") and vcard.email_list:
            vals["email"] = vcard.email_list[0].value

        if hasattr(vcard, "tel_list"):
            commands = []
            for tel in vcard.tel_list:
                tel_type_raw = getattr(tel, "type_param", "")
                if isinstance(tel_type_raw, list):
                    tel_type = ",".join(str(t) for t in tel_type_raw).upper()
                elif isinstance(tel_type_raw, str):
                    tel_type = tel_type_raw.upper()
                else:
                    tel_type = ""

                value = (tel.value or "").strip()
                if not value:
                    continue
                if "CELL" in tel_type or "MOBILE" in tel_type:
                    phone_type = "mobile"
                elif "FAX" in tel_type:
                    phone_type = "fax"
                else:
                    phone_type = "landline"
                commands.append(
                    Command.create(
                        {
                            "number": value,
                            "type": phone_type,
                            "primary": tel.params.get("PREF") == ["1"],
                        }
                    )
                )
            if commands:
                vals["phone_ids"] = commands

        if hasattr(vcard, "adr"):
            adr = vcard.adr.value
            self._parse_address(adr, vals, env)
        elif hasattr(vcard, "adr_list") and vcard.adr_list:
            work_adr = None
            for adr_item in vcard.adr_list:
                if (
                    hasattr(adr_item, "type_param")
                    and "WORK" in adr_item.type_param.upper()
                ):
                    work_adr = adr_item.value
                    break
            if not work_adr:
                work_adr = vcard.adr_list[0].value
            self._parse_address(work_adr, vals, env)

        if hasattr(vcard, "org"):
            org_name = (
                vcard.org.value[0]
                if isinstance(vcard.org.value, list)
                else vcard.org.value
            )
            if env and org_name:
                company = (
                    env["res.partner"]
                    .sudo()
                    .search(
                        [("name", "=", org_name), ("is_company", "=", True)],
                        limit=1,
                    )
                )
                if company:
                    vals["parent_id"] = company.id

        if hasattr(vcard, "title"):
            vals["function"] = vcard.title.value

        if hasattr(vcard, "url"):
            vals["website"] = vcard.url.value
        elif hasattr(vcard, "url_list") and vcard.url_list:
            vals["website"] = vcard.url_list[0].value

        if hasattr(vcard, "photo"):
            try:
                photo_value = vcard.photo.value
                if isinstance(photo_value, bytes):
                    vals["image_128"] = base64.b64encode(photo_value).decode()
            except (TypeError, ValueError) as e:
                _logger.warning("Failed to parse photo: %s", e)

        if hasattr(vcard, "categories") and env:
            try:
                cat_names = vcard.categories.value
                if cat_names:
                    Tag = env["res.partner.tag"].sudo()
                    names = list(dict.fromkeys(str(name) for name in cat_names))
                    by_name = {}
                    for tag in Tag.search([("name", "in", names)]):
                        by_name.setdefault(tag.name, tag)
                    missing = [name for name in names if name not in by_name]
                    for tag in Tag.create([{"name": name} for name in missing]):
                        by_name[tag.name] = tag
                    vals["category_id"] = [
                        Command.set([by_name[name].id for name in names])
                    ]
            except (TypeError, ValueError) as e:
                _logger.warning("Failed to parse categories: %s", e)

        if hasattr(vcard, "note"):
            vals["comment"] = vcard.note.value

        if hasattr(vcard, "bday"):
            try:
                bday_value = vcard.bday.value
                if isinstance(bday_value, str):
                    bday_date = datetime.strptime(bday_value, "%Y%m%d").date()
                    vals["birthdate"] = bday_date
            except (TypeError, ValueError) as e:
                _logger.warning("Failed to parse birthday: %s", e)

        if hasattr(vcard, "x_odoo_type"):
            vals["is_company"] = vcard.x_odoo_type.value == "company"

        return vals

    def _parse_address(self, adr, vals, env):
        if hasattr(adr, "street"):
            street_lines = adr.street.split("\n") if adr.street else []
            if len(street_lines) >= 1:
                vals["street"] = street_lines[0]
            if len(street_lines) >= 2:
                vals["street2"] = street_lines[1]

        if hasattr(adr, "city"):
            vals["city"] = adr.city

        if hasattr(adr, "code"):
            vals["zip"] = adr.code

        if env:
            if hasattr(adr, "region") and adr.region:
                state = (
                    env["res.country.state"]
                    .sudo()
                    .search([("name", "ilike", adr.region)], limit=1)
                )
                if state:
                    vals["state_id"] = state.id

            if hasattr(adr, "country") and adr.country:
                country = (
                    env["res.country"]
                    .sudo()
                    .search(
                        [
                            "|",
                            ("name", "ilike", adr.country),
                            ("code", "=ilike", adr.country),
                        ],
                        limit=1,
                    )
                )
                if country:
                    vals["country_id"] = country.id
