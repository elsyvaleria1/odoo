import unicodedata

from odoo import models
from odoo.exceptions import UserError


def _person(name):
    """A name as people write it by hand: no accents, case or extra spaces.

    :param name: the name as captured, or False
    :rtype: str
    """
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _has_delivery_proof(self):
        # The customer may sign on the driver's phone instead of on the paper: the
        # signature counts with the name of whoever received, if it is not ours.
        return super()._has_delivery_proof() or not self._customer_signature_problem()

    def _customer_signature_problem(self):
        """Why the signature on this transfer is not the customer's.

        The system checks that it carries the name of whoever received, and that
        the name is not the driver's, the supervisor's, the salesperson's nor that
        of whoever validates. That the stroke is the customer's is the reviewer's
        call, on the transfer.

        :return: the reason, empty when the signature counts
        :rtype: str
        """
        self.check_singleton()
        if not self.signature:
            return self.env._("it carries no signature")
        receiver = _person(self.trip_receiver_name)
        if not receiver:
            return self.env._("the name of whoever received is missing")
        trip = self.batch_id
        ours = (
            (self.env._("the driver"), trip.driver_id.name),
            (self.env._("the trip supervisor"), trip.supervisor_id.name),
            (self.env._("the salesperson"), self.sale_id.user_id.name),
            (self.env._("whoever validates"), self.env.user.name),
        )
        for role, name in ours:
            if name and receiver == _person(name):
                return self.env._(
                    "the name of whoever received is %(role)s's", role=role
                )
        return ""

    def _check_delivery_proof(self):
        # A signature that does not count says why, before the refusal that asks
        # for the photo: the driver's phone shows this reason as is.
        for picking in self:
            if (
                picking._requires_delivery_proof()
                and not picking.delivery_proof
                and picking.signature
                and (problem := picking._customer_signature_problem())
            ):
                raise UserError(
                    self.env._(
                        "The signature on %(name)s does not count as the "
                        "customer's: %(problem)s. Capture the name of whoever "
                        "received, or upload the photo of the delivery slip signed "
                        "by the customer.",
                        name=picking.name,
                        problem=problem,
                    )
                )
        return super()._check_delivery_proof()
