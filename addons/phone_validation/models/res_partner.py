from collections.abc import Set as AbstractSet

from odoo import api, models

COLLECTION_TYPES = (list, tuple, AbstractSet)


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["mixin.mail.thread.phone", "res.partner"]

    def _phone_replace_number(self, fname, number, *types):
        self.check_singleton()
        current = self._phone_get_number()
        if fname != "phone_ids" or (
            types and current != self._phone_get_number(*types)
        ):
            return super()._phone_replace_number(fname, number, *types)
        if number == current.number:
            return None
        replacement = self.env["phone.number"]
        if number:
            replacement = replacement.create(
                {"number": number, "type": current.type or "mobile"}
            )
        self.write(self._prepare_phone_replacement_vals(replacement))
        return None

    @property
    def _rec_names_search(self):
        return [*super()._rec_names_search, "phone_mobile_search"]

    @api.model
    def _search_display_name_match(self, operator, value, search_fnames):
        if "phone_mobile_search" in search_fnames and (
            self._phone_term_too_short(value) or not self._phone_term_has_digit(value)
        ):
            search_fnames = [
                fname for fname in search_fnames if fname != "phone_mobile_search"
            ]
        return super()._search_display_name_match(operator, value, search_fnames)

    @api.model
    def _phone_term_has_digit(self, value) -> bool:
        values = value if isinstance(value, COLLECTION_TYPES) else [value]
        return any(
            not isinstance(term, str) or any(ch.isdigit() for ch in term)
            for term in values
        )

    @api.model
    def _phone_term_too_short(self, value) -> bool:
        minimum = self._phone_search_min_length
        if not minimum:
            return False
        values = value if isinstance(value, COLLECTION_TYPES) else [value]
        return any(
            isinstance(term, str) and 0 < len(term.strip()) < minimum for term in values
        )
