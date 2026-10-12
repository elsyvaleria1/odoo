import re
from collections import defaultdict
from typing import Any, Self

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL, frozendict

_debug = DebugLog(__name__)

PHONE_NOISE_PATTERN = re.compile(r"[\s\\./\(\)\-]")


PHONE_TYPES = [
    ("mobile", "Mobile"),
    ("landline", "Landline"),
    ("fax", "Fax"),
    ("whatsapp", "WhatsApp"),
    ("emergency", "Emergency"),
]


def _many2many_commands(value: Any) -> list:
    if isinstance(value, models.BaseModel):
        return [Command.set(value.ids)]
    if isinstance(value, tuple):
        return [Command.set(value)]
    if not value:
        return []
    if not any(isinstance(item, (tuple, list, dict)) for item in value):
        return [Command.set(value)]
    return [
        Command.create(item)
        if isinstance(item, dict)
        else item
        if isinstance(item, (tuple, list))
        else Command.link(item)
        for item in value
    ]


class PhoneNumber(models.Model):
    _name = "phone.number"
    _description = "Phone Number"
    _order = "primary desc, sequence, id"
    _rec_name = "number"
    _rec_names_search = ["number", "sanitized", "label"]
    _name_create_on_import = True
    _access_anchors = frozendict(
        {
            "partner": "partner_ids",
        }
    )

    number = fields.Char(required=True)
    sanitized = fields.Char(
        compute="_compute_sanitized",
        store=True,
        index=True,
        readonly=True,
    )
    type = fields.Selection(
        selection=PHONE_TYPES,
        default="mobile",
        required=True,
    )
    country_id = fields.Many2one(comodel_name="res.country")
    country_inferred = fields.Boolean(
        help="The country was read from the contact the number was created for, "
        "and follows that contact's corrections while no other contact holds "
        "the number. Choosing a country on the number clears it.",
    )
    primary = fields.Boolean(default=False)
    sequence = fields.Integer(default=10)
    label = fields.Char()
    note = fields.Text()
    active = fields.Boolean(default=True)
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="res_partner_phone_number_rel",
        column1="phone_number_id",
        column2="partner_id",
        string="Contacts",
    )

    _unique_sanitized = models.Constraint(
        "unique(sanitized)",
        "This phone number already exists.",
    )

    @api.model
    def _normalize_number(self, number: str, country=None) -> str:
        number = PHONE_NOISE_PATTERN.sub("", number or "")
        if number.startswith("00"):
            _debug.logic("sanitize_prefix_rewritten", country=bool(country))
            number = "+" + number[2:]
        return number

    @api.depends("number", "country_id")
    def _compute_sanitized(self) -> None:
        _debug.perf.count("sanitized_computed", phones=len(self))
        for phone in self:
            phone.sanitized = self._normalize_number(phone.number, phone.country_id)

    @api.depends("number", "label", "type")
    def _compute_display_name(self) -> None:
        for phone in self:
            phone.display_name = (
                f"{phone.number} ({phone.label})" if phone.label else phone.number
            )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        vals_list = [self._with_inferred_country(vals) for vals in vals_list]
        Country = self.env["res.country"]
        wanted = [
            self._normalize_number(
                vals.get("number"), Country.browse(vals["country_id"])
            )
            for vals in vals_list
        ]
        existing = {
            phone.sanitized: phone
            for phone in self.with_context(active_test=False).search(
                [("sanitized", "in", [s for s in wanted if s])]
            )
        }
        to_create, by_position = [], {}
        first_position, deferred = {}, []
        for position, (vals, sanitized) in enumerate(
            zip(vals_list, wanted, strict=True)
        ):
            if phone := existing.get(sanitized):
                _debug.logic("create_reused", position=position, phone=phone.id)
                phone._link_existing(vals)
                by_position[position] = phone
            elif sanitized and sanitized in first_position:
                _debug.logic(
                    "create_deduplicated",
                    position=position,
                    first=first_position[sanitized],
                )
                deferred.append((position, first_position[sanitized], vals))
            else:
                to_create.append((position, vals))
                first_position[sanitized] = position
        created = super().create([vals for _, vals in to_create])
        _debug.lifecycle(
            "create",
            requested=len(vals_list),
            reused=len(existing),
            deduplicated=len(deferred),
            created=len(created),
        )
        for (position, _), phone in zip(to_create, created, strict=True):
            by_position[position] = phone
        for position, first, vals in deferred:
            phone = by_position[first]
            phone._link_existing(vals)
            by_position[position] = phone
        return self.browse(by_position[i].id for i in range(len(vals_list)))

    def write(self, vals: ValuesType) -> bool:
        if "country_id" in vals and "country_inferred" not in vals:
            vals = {**vals, "country_inferred": False}
        return super().write(vals)

    @api.model
    def _with_inferred_country(self, vals: ValuesType) -> ValuesType:
        if vals.get("country_id"):
            _debug.logic("country_from_vals", by="country_id")
            return vals
        country = self._get_contact_country_from_vals(vals)
        return {**vals, "country_id": country.id, "country_inferred": True}

    @api.model
    def _get_contact_country_from_vals(self, vals: ValuesType):
        partner_ids = [
            id_
            for command in _many2many_commands(vals.get("partner_ids"))
            for id_ in (
                command[2]
                if command[0] == Command.SET
                else [command[1]]
                if command[0] == Command.LINK
                else []
            )
        ]
        _debug.logic("country_from_vals", by="partner", partners=len(partner_ids))
        return self.env["res.partner"].browse(partner_ids[:1]).country_id

    def _link_existing(self, vals: ValuesType) -> None:
        relational = {
            fname: [
                Command.link(id_)
                for command in commands
                if command[0] == Command.SET
                for id_ in command[2]
            ]
            + [command for command in commands if command[0] != Command.SET]
            for fname, value in vals.items()
            if self._fields[fname].type == "many2many"
            and (commands := _many2many_commands(value))
        }
        if not self.active:
            relational["active"] = True
        _debug.logic(
            "link_existing",
            phone=self.id,
            reactivated=not self.active,
            fields=list(relational),
        )
        if relational:
            self.write(relational)

    def _primary(self, *types: str) -> Self:
        candidates = (
            self.filtered(lambda p: p.type in types) if types else self
        ) or self
        _debug.logic(
            "primary_resolved",
            phones=len(self),
            types=list(types),
            fallback=bool(types) and candidates is self,
        )
        return candidates[:1]

    def _update_country_from_contact(self) -> None:
        phones = self.filtered("country_inferred")
        if not phones:
            return
        self.env["res.partner"].flush_model(["country_id", "phone_ids"])
        self.flush_model(["partner_ids", "sanitized"])
        self.env.cr.execute(
            SQL(
                """
                SELECT rel.phone_number_id, MIN(rel.partner_id), MIN(partner.country_id)
                  FROM res_partner_phone_number_rel AS rel
                  JOIN res_partner AS partner ON partner.id = rel.partner_id
                 WHERE rel.phone_number_id = ANY(%s)
                 GROUP BY rel.phone_number_id
                HAVING COUNT(*) = 1 AND MIN(partner.country_id) IS NOT NULL
                """,
                phones.ids,
            )
        )
        rereads = {}
        for phone_id, contact_id, country_id in self.env.cr.fetchall():
            phone = self.browse(phone_id)
            if phone.country_id.id != country_id:
                country = self.env["res.country"].browse(country_id)
                rereads[phone] = (
                    country,
                    contact_id,
                    self._normalize_number(phone.number, country),
                )
        _debug.logic("country_rereads", phones=len(self), rereads=len(rereads))
        if not rereads:
            return
        changing = {
            sanitized
            for phone, (_, _, sanitized) in rereads.items()
            if sanitized != phone.sanitized
        }
        holders = {}
        if changing:
            self.env.cr.execute(
                SQL(
                    "SELECT sanitized, id FROM phone_number"
                    " WHERE sanitized = ANY(%s) AND id != ALL(%s)",
                    list(changing),
                    [phone.id for phone in rereads],
                )
            )
            holders = {
                sanitized: self.browse(id_) for sanitized, id_ in self.env.cr.fetchall()
            }
        leaving = {phone.sanitized for phone in rereads}
        privileged = self.sudo()
        moved = defaultdict(privileged.browse)
        for phone, (country, contact_id, sanitized) in rereads.items():
            holder = holders.get(sanitized)
            if sanitized == phone.sanitized or not (holder or sanitized in leaving):
                moved[country] |= privileged.browse(phone.id)
                holders[sanitized] = phone
            elif holder and holder.with_user(self.env.user).has_access("read"):
                privileged.browse(phone.id)._merge_into(
                    privileged.browse(holder.id),
                    self.env["res.partner"].browse(contact_id),
                )
            else:
                _debug.logic(
                    "country_reread_skipped",
                    phone=phone.id,
                    holder=holder.id if holder else None,
                    reason="unreadable_holder" if holder else "number_leaving",
                )
        for country, to_move in moved.items():
            _debug.lifecycle("country_reread", phones=to_move.ids, country=country.id)
            to_move.write({"country_id": country.id, "country_inferred": True})

    def _merge_into(self, holder: Self, contact) -> None:
        self.check_singleton()
        _debug.lifecycle(
            "merged_into_holder", phone=self.id, holder=holder.id, contact=contact.id
        )
        self.env["mixin.merge"]._update_foreign_keys_generic(self._name, self, holder)
        if not holder.active:
            holder.active = True
        self.unlink()
        contact.modified(["phone_ids"])
