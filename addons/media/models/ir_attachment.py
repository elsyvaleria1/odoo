import logging

from odoo import models
from odoo.libs.documents import can_decode_media, media_duration_ms

_logger = logging.getLogger(__name__)


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    def _media_length_ms(self) -> int:
        """How long the recording plays, read from its container; 0 unknown."""
        self.check_singleton()
        if not can_decode_media():
            return 0
        data = self._get_content()
        if not data:
            return 0
        try:
            return media_duration_ms(data)
        except Exception as error:
            _logger.info("Could not read the length of %s: %s", self.name, error)
            return 0
