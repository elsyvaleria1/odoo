from typing import Self

from odoo import api, models
from odoo.fields import Domain


class MixinCalendarPrivacy(models.AbstractModel):
    """Delegate record visibility to the ``calendar.event`` a record hangs off."""

    _name = "mixin.calendar.privacy"
    _description = "Calendar Privacy Delegation"

    _privacy_event_fname = "event_id"
    _search_visibility_fields = ()

    @api.model
    def _get_domain_privacy(self) -> Domain:
        events = self.env["calendar.event"]
        return Domain(
            self._privacy_event_fname,
            "any",
            Domain(events._get_domain_default_privacy()),
        )

    def _privacy_hidden(self) -> Self:
        if not self:
            return self
        fname = self._privacy_event_fname
        events = self[fname].sudo()
        hidden_ids = set(
            events.filtered(lambda event: event._check_private_event_conditions()).ids
        )
        if not hidden_ids:
            return self.browse()
        return self.filtered(
            lambda record: (
                (linked := record[fname].ids) and not set(linked) - hidden_ids
            )
        )

    def _search(
        self,
        domain,
        offset=0,
        limit=None,
        order=None,
        *,
        active_test=True,
        bypass_access=False,
    ):
        if not (self.env.su or bypass_access):
            domain = Domain.AND([domain, self._get_domain_privacy()])
        return super()._search(
            domain,
            offset=offset,
            limit=limit,
            order=order,
            active_test=active_test,
            bypass_access=bypass_access,
        )
