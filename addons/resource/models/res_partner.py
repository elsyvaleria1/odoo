from typing import TYPE_CHECKING

from odoo import fields, models

if TYPE_CHECKING:
    from .resource_resource import ResourceResource
    from odoo.addons.base.models.res_company import ResCompany


class ResPartner(models.Model):
    _inherit = "res.partner"

    resource_ids = fields.One2many(
        comodel_name="resource.resource",
        inverse_name="partner_id",
        string="Resources",
    )
    # what a person IS lives on the private facet of their party, a child of
    # type private behind base's guard, where it shows to no one but its readers
    place_of_birth = fields.Char()
    country_of_birth = fields.Many2one(comodel_name="res.country")
    nationality_ids = fields.One2many(
        comodel_name="resource.nationality",
        inverse_name="partner_id",
        string="Nationalities",
    )

    def _get_private_facets(self) -> dict:
        # searched as the reader, so base's guard hides a facet they may not see
        facets = self.search(
            [("parent_id", "in", self.ids), ("type", "=", "private")], order="id desc"
        )
        return {facet.parent_id: facet for facet in facets}

    def _get_private_facet(self):
        if not self:
            return self
        self.check_singleton()
        return self._get_private_facets().get(self, self.browse())

    def _ensure_private_facet(self):
        self.check_singleton()
        return self._get_private_facet() or self.create(
            {"parent_id": self.id, "type": "private"}
        )

    def _get_resources(self, company: ResCompany) -> ResourceResource:
        return (
            self.env["resource.resource"]
            .with_context(active_test=False)
            .search(
                [
                    ("partner_id", "in", self.ids),
                    ("type", "=", "human"),
                    ("company_id", "=", company.id),
                ]
            )
        )

    def _get_or_create_resources(self, company: ResCompany) -> ResourceResource:
        resource_by_party = {
            resource.partner_id: resource for resource in self._get_resources(company)
        }
        missing = self.browse(
            list(dict.fromkeys(p.id for p in self if p not in resource_by_party))
        )
        created = self.env["resource.resource"].create(
            [
                {
                    "partner_id": party.id,
                    "type": "human",
                    "company_id": company.id,
                }
                for party in missing
            ]
        )
        resource_by_party.update(zip(missing, created, strict=True))
        return self.env["resource.resource"].browse(
            [resource_by_party[party].id for party in self]
        )
