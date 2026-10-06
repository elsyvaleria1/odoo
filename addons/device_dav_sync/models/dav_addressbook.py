import ast
import hashlib
import logging

from odoo import api, fields, models
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)


class DAVAddressbook(models.Model):
    _name = "dav.addressbook"
    _description = "DAV Addressbook Collection"
    _order = "sequence, name"
    _access_anchors = frozendict(
        {
            "owner": "user_id",
        }
    )

    name = fields.Char(
        string="Addressbook Name",
        translate=True,
        required=True,
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(translate=True)

    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Owner",
        default=lambda self: self.env.user,
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
    )

    collection_uid = fields.Char(
        string="Collection UID",
        index=True,
        copy=False,
        readonly=True,
        required=True,
    )
    ctag = fields.Char(
        string="Collection Tag",
        compute="_compute_ctag",
        store=False,
        help="Changes when any contact in collection is modified (always computed fresh)",
    )

    contact_domain = fields.Text(
        string="Contact Filter",
        default="[]",
        help="Odoo domain to filter contacts in this addressbook",
    )
    include_company_contacts = fields.Boolean(
        default=False,
        help="Include all contacts from user's company",
    )

    contact_count = fields.Integer(compute="_compute_ctag")

    @api.depends("name", "user_id")
    def _compute_display_name(self):
        for addressbook in self:
            addressbook.display_name = (
                f"{addressbook.name} ({addressbook.user_id.name})"
            )

    @api.depends("user_id", "contact_domain", "include_company_contacts")
    def _compute_ctag(self) -> None:
        Partner = self.env["res.partner"].with_context(active_test=False)
        for addressbook in self:
            [(count, latest)] = Partner._read_group(  # noqa: E8507 - each address book counts its own domain
                addressbook._get_domain_contact(),
                aggregates=["__count", "write_date:max"],
            )
            addressbook.contact_count = count
            addressbook.ctag = (
                hashlib.md5(f"{count}-{latest}".encode()).hexdigest()[:16]
                if count
                else "empty"
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if "collection_uid" not in vals:
                seq = self.env["ir.sequence"].next_by_code("dav.collection.uid")
                vals["collection_uid"] = f"addressbook-{seq}"
        return super().create(vals_list)

    def _get_domain_contact(self):
        self.check_singleton()

        try:
            domain = ast.literal_eval(self.contact_domain or "[]")
            if not isinstance(domain, list):
                _logger.warning(
                    "Invalid contact_domain in addressbook %s: Expected list, got %s",
                    self.id,
                    type(domain).__name__,
                )
                domain = []
        except (ValueError, SyntaxError) as e:
            _logger.warning("Invalid contact_domain in addressbook %s: %s", self.id, e)
            domain = []

        if self.include_company_contacts:
            domain += [
                "|",
                ("company_id", "=", self.company_id.id),
                ("company_id", "=", False),
            ]
        else:
            domain.append(("user_id", "=", self.user_id.id))

        return domain

    @api.model
    def _provision_default_addressbooks(self, user) -> None:
        if self.search_count([("user_id", "=", user.id)], limit=1):
            return
        for spec in self._get_addressbook_specs(user):
            self.create(
                {
                    "name": spec["name"],
                    "user_id": user.id,
                    "company_id": user.company_id.id,
                    "contact_domain": spec.get("contact_domain", "[]"),
                    "include_company_contacts": spec.get(
                        "include_company_contacts", False
                    ),
                    "sequence": spec.get("sequence", 10),
                }
            )

    def _get_addressbook_specs(self, user):
        specs = [
            {
                "name": "My Contacts",
                "contact_domain": "[]",
                "include_company_contacts": False,
                "sequence": 5,
            }
        ]
        if self._user_in_group(user, "sale.group_sale_salesman"):
            specs.append(
                {
                    "name": "My Customers",
                    "contact_domain": "[('customer_rank', '>', 0)]",
                    "include_company_contacts": False,
                    "sequence": 10,
                }
            )
        if self._user_in_group(user, "purchase.group_purchase_user"):
            specs.append(
                {
                    "name": "Vendors",
                    "contact_domain": "[('supplier_rank', '>', 0)]",
                    "include_company_contacts": True,
                    "sequence": 20,
                }
            )
        if self._user_in_group(user, "device_dav_sync.group_dav_sync_all"):
            specs.append(
                {
                    "name": "All Company Contacts",
                    "contact_domain": "[]",
                    "include_company_contacts": True,
                    "sequence": 30,
                }
            )
        return specs

    def _user_in_group(self, user, group_xmlid) -> bool:
        group = self.env.ref(group_xmlid, raise_if_not_found=False)
        return bool(group and group in user.all_group_ids)

    def get_contacts(self):
        self.check_singleton()
        domain = self._get_domain_contact()
        return self.env["res.partner"].search(domain)

    def action_view_contacts(self):
        self.check_singleton()
        domain = self._get_domain_contact()
        return {
            "type": "ir.actions.act_window",
            "name": f"{self.name} - Contacts",
            "res_model": "res.partner",
            "view_mode": "list,form",
            "domain": domain,
            "context": {"default_user_id": self.user_id.id},
        }
