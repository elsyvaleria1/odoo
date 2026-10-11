import logging

from odoo import api, models

from ..tools.cache import doc_cache_generation, stale_index_domain

logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.autovacuum
    def _gc_doc_index(self) -> None:
        stale = self.search(stale_index_domain(doc_cache_generation(self.env)))
        if stale:
            stale.unlink()
            logger.info("GC'd %s /doc cached index", len(stale))
