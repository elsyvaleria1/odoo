from odoo import models
from odoo.tools import ormcache
from odoo.tools.json import scriptsafe as json_scriptsafe


class ResCompany(models.Model):
    _inherit = "res.company"

    def _prepare_default_pricelist_vals(self):
        values = super()._prepare_default_pricelist_vals()
        values["website_id"] = False
        return values

    def _get_cache_invalidation_fields(self):
        return super()._get_cache_invalidation_fields() | {"name"}

    @ormcache("self.id")
    def _get_name_cached(self):
        self.check_singleton()
        return self.name

    def _get_organization_markup(self, base_url):
        self.check_singleton()
        return json_scriptsafe.dumps(
            {
                "@context": "http://schema.org",
                "@type": "Organization",
                "name": self._get_name_cached(),
                "logo": f"{base_url}/logo.png?company={self.id}",
                "url": base_url,
            },
            indent=2,
        )
