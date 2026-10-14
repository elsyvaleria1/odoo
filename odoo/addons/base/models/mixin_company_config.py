from typing import Self

from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict, ormcache

_debug = DebugLog(__name__)


class MixinCompanyConfig(models.AbstractModel):
    _name = "mixin.company.config"
    _description = "Configuration an application keeps per company"
    _check_company_auto = True
    _company_config = True

    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
        ondelete="cascade",
    )

    _company_uniq = models.Constraint(
        "unique (company_id)",
        "A company has one configuration record per application.",
    )

    @api.model
    def _get_field_names_delegated_to_root(self) -> list[str]:
        return []

    @api.constrains(
        lambda self: self._get_field_names_delegated_to_root() + ["company_id"]
    )
    def _check_delegated_fields_match_root(self) -> None:
        for config in self:
            parent = config.company_id.parent_id
            if not parent:
                continue
            parent_config = self._for(parent).sudo()
            for fname in self._get_field_names_delegated_to_root():
                if config[fname] != parent_config[fname]:
                    description = (
                        self.env["ir.model.fields"]
                        ._get(self._name, fname)
                        .field_description
                    )
                    raise ValidationError(
                        self.env._(
                            "The %s of a subsidiary must be the same as its root company.",
                            description,
                        )
                    )

    def _inherit_delegated_fields(self, vals_list: list[ValuesType]) -> None:
        delegated = self._get_field_names_delegated_to_root()
        if not delegated:
            return
        Company = self.env["res.company"]
        for vals in vals_list:
            parent = Company.browse(vals.get("company_id")).parent_id
            if not parent:
                continue
            parent_config = self._for(parent).sudo()
            for fname in delegated:
                vals.setdefault(
                    fname,
                    self._fields[fname].convert_to_write(
                        parent_config[fname], parent_config
                    ),
                )

    @api.model_create_multi
    def create(self, vals_list: list[ValuesType]) -> Self:
        if any("company_id" not in vals for vals in vals_list):
            default = self.default_get(["company_id"]).get("company_id")
            vals_list = [{"company_id": default, **vals} for vals in vals_list]
        self._inherit_delegated_fields(vals_list)
        company_ids = [vals.get("company_id") for vals in vals_list]
        existing = {
            config.company_id.id: config
            for config in self.sudo().search(
                [("company_id", "in", [cid for cid in company_ids if cid])]
            )
        }
        if not existing:
            records = super().create(vals_list)
            self.env.registry.clear_cache()
            for vals in vals_list:
                self._clear_registry_cache_for(vals)
            return records
        config_ids = []
        to_create = []
        for vals in vals_list:
            config = existing.get(vals.get("company_id"))
            if config is None:
                to_create.append(vals)
                config_ids.append(None)
                continue
            _debug.lifecycle(
                "written_instead_of_created",
                model=self._name,
                company=config.company_id.id,
            )
            config.with_env(self.env).write(
                {key: value for key, value in vals.items() if key != "company_id"}
            )
            config_ids.append(config.id)
        created = iter(super().create(to_create).ids if to_create else ())
        if to_create:
            self.env.registry.clear_cache()
        for vals in vals_list:
            self._clear_registry_cache_for(vals)
        return self.browse(
            [
                next(created) if config_id is None else config_id
                for config_id in config_ids
            ]
        )

    def write(self, vals: ValuesType) -> bool:
        result = super().write(vals)
        if "company_id" in vals:
            self.env.registry.clear_cache()
        self._clear_registry_cache_for(vals)
        self._propagate_delegated_fields_to_branches(vals)
        return result

    def _propagate_delegated_fields_to_branches(self, vals: ValuesType) -> None:
        delegated = set(vals) & set(self._get_field_names_delegated_to_root())
        if not delegated:
            return
        roots = self.filtered(lambda config: not config.company_id.parent_id)
        if not roots:
            return
        branches = (
            self.env["res.company"]
            .with_privilege(
                "base.privilege_read_company_hierarchy",
                reason="find the branches a root configuration's value reaches",
            )
            .with_context(active_test=False)
            .search(
                [
                    ("id", "child_of", roots.company_id.ids),
                    ("id", "not in", roots.company_id.ids),
                ]
            )
        )
        if not branches:
            return
        _debug.logic(
            "delegated_fields_propagated",
            model=self._name,
            fields=sorted(delegated),
            branches=len(branches),
        )
        self._for_each(branches.with_env(self.env)).write(
            {fname: vals[fname] for fname in delegated}
        )

    def unlink(self) -> bool:
        result = super().unlink()
        self.env.registry.clear_cache()
        return result

    def _clear_registry_cache_for(self, vals: ValuesType) -> None:
        invalidation_fields = self._get_cache_invalidation_fields()
        if invalidation_fields.isdisjoint(vals):
            return
        _debug.lifecycle(
            "registry_cache_cleared",
            model=self._name,
            fields=sorted(invalidation_fields & set(vals)),
        )
        self.env.registry.clear_cache()

    @api.model
    def _get_cache_invalidation_fields(self) -> set[str]:
        return set()

    @api.model
    def _for(self, company: models.Model) -> Self:
        company.check_singleton()
        return self._for_each(company)

    @api.model
    @ormcache()
    def _config_ids_by_company(self) -> frozendict:
        configs = (
            self.sudo().with_context(active_test=False).search_fetch([], ["company_id"])
        )
        return frozendict((config.company_id.id, config.id) for config in configs)

    @api.model
    def _for_each(self, companies: models.Model) -> Self:
        return self.browse(list(self._config_id_by_company(companies).values()))

    @api.model
    def _config_id_by_company(self, companies: models.Model) -> dict[int, int]:
        companies = companies.filtered(lambda company: isinstance(company.id, int))
        by_company = self._config_ids_by_company()
        found = {cid: by_company[cid] for cid in companies.ids if cid in by_company}
        unmapped = companies.filtered(lambda company: company.id not in by_company)
        if not unmapped:
            return found
        existing = (
            self.sudo()
            .with_context(active_test=False)
            .search_fetch([("company_id", "in", unmapped.ids)], ["company_id"])
        )
        if existing:
            self.env.registry.clear_cache()
        missing = unmapped - existing.company_id
        if missing:
            _debug.lifecycle(
                "created_for_companies", model=self._name, companies=missing.ids
            )
            existing |= self.sudo().create(
                [{"company_id": company.id} for company in missing]
            )
        found.update((config.company_id.id, config.id) for config in existing)
        return found
