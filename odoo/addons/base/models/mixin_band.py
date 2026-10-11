from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinBand(models.AbstractModel):
    _name = "mixin.band"
    _description = "Numeric Band Mixin"

    _band_allow_negative = False

    min_value = fields.Float(
        default=0.0,
        help="Lower bound of the band, inclusive.",
    )
    max_value = fields.Float(
        default=0.0,
        help="Upper bound of the band, exclusive -- it is the lower bound of "
        "the next band. 0 means no upper limit, which the highest band of a "
        "scale should use so nothing falls off the top; on a band starting "
        "below zero, 0 is the bound itself.",
    )
    active = fields.Boolean(default=True)

    def _is_band(self) -> bool:
        return True

    def _get_domain_band_scope(self):
        self.check_singleton()
        return []

    @api.model
    def _get_band_scope_fields(self) -> tuple[str, ...]:
        return ()

    def _get_upper_bound(self) -> float:
        self.check_singleton()
        if self.max_value or self.min_value < 0:
            return self.max_value
        return float("inf")

    @staticmethod
    def _is_range_overlapping(band_a, band_b) -> bool:
        return (
            band_a.min_value < band_b._get_upper_bound()
            and band_b.min_value < band_a._get_upper_bound()
        )

    def _is_covering(self, value) -> bool:
        self.check_singleton()
        return self.min_value <= value < self._get_upper_bound()

    @api.constrains(
        lambda self: (
            "min_value",
            "max_value",
            "active",
            *self._get_band_scope_fields(),
        )
    )
    def _check_band(self) -> None:
        scales = defaultdict(self.browse)
        for record in self:
            if not record._is_band():
                if record.min_value or record.max_value:
                    _debug.logic(
                        "band_rejected",
                        model=self._name,
                        record=record.id,
                        reason="bounds_on_non_band",
                    )
                    raise ValidationError(
                        self.env._(
                            "%(name)s: bounds only apply to a band.",
                            name=record.display_name,
                        )
                    )
                continue
            if record.min_value < 0 and not self._band_allow_negative:
                _debug.logic(
                    "band_rejected",
                    model=self._name,
                    record=record.id,
                    reason="negative_lower_bound",
                )
                raise ValidationError(
                    self.env._(
                        "%(name)s: the lower bound cannot be negative.",
                        name=record.display_name,
                    )
                )
            if record._get_upper_bound() <= record.min_value:
                _debug.logic(
                    "band_rejected",
                    model=self._name,
                    record=record.id,
                    reason="upper_not_above_lower",
                )
                raise ValidationError(
                    self.env._(
                        "%(name)s: the upper bound (%(max)s) must be greater "
                        "than the lower bound (%(min)s), or zero for an "
                        "open-ended band.",
                        name=record.display_name,
                        max=record.max_value,
                        min=record.min_value,
                    )
                )
            if not record.active:
                continue
            scales[repr(record._get_domain_band_scope())] |= record

        _debug.pipeline(
            "band_overlap_check",
            model=self._name,
            records=len(self),
            scales=len(scales),
        )
        for records in scales.values():
            candidates = records.search(records[0]._get_domain_band_scope())
            _debug.perf.count(
                "band_scale_candidates", model=self._name, candidates=len(candidates)
            )
            for record in records:
                for other in candidates:
                    if other == record or not other._is_band():
                        continue
                    if record._is_range_overlapping(record, other):
                        _debug.logic(
                            "band_rejected",
                            model=self._name,
                            record=record.id,
                            other=other.id,
                            reason="overlap",
                        )
                        raise ValidationError(
                            self.env._(
                                "%(a)s overlaps with %(b)s.",
                                a=record.display_name,
                                b=other.display_name,
                            )
                        )
