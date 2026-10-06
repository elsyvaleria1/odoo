from collections import defaultdict
from datetime import date, datetime

import babel.dates
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, date_utils, format_date
from odoo.tools.misc import get_lang

# babel patterns, so a label is in the user's language, not the host's locale
DISPLAY_FORMATS = {
    "day": "dd MMM y",
    "month": "MMMM y",
    "year": "y",
}


class Base(models.AbstractModel):
    _inherit = "base"

    @api.model
    def get_cohort_data(
        self, date_start, date_stop, measure, interval, domain, mode, timeline
    ) -> dict:
        """
        Get all the data needed to display a cohort view

        :param date_start: the starting date to use in the group_by clause
        :param date_stop: the date field which mark the change of state
        :param measure: the field to aggregate
        :param interval: the interval of time between two cells ('day', 'week', 'month', 'quarter', 'year')
        :param domain: a domain to limit the _read_group
        :param mode: the mode of aggregation ('retention', 'churn')
        :param timeline: the direction to display data ('forward', 'backward')
        :return: dictionary with 'rows' (a list of rows, each holding up to 16 cells)
                 and 'avg' (average value and per-column averages).
        :rtype: dict
        """
        rows = []
        columns_avg = defaultdict(lambda: {"percentage": 0, "count": 0})
        total_value = 0
        initial_churn_value = 0
        domain = Domain(domain)
        if measure != "__count":
            field = self._fields.get(measure)
            if field is None:
                raise UserError(
                    self.env._(
                        "The field %(measure)s does not exist on %(model)s.",
                        measure=measure,
                        model=self._name,
                    )
                )
            if field.type != "many2one" and field.aggregator != "sum":
                raise UserError(
                    self.env._(
                        "The field %(measure)s can't be used as a measure.",
                        measure=measure,
                    )
                )
            domain &= Domain(measure, "!=", False)
            measures = [f"{measure}:sum"]
            if field.type == "many2one":
                measure = f"{measure}:count_distinct"
            else:
                measure = f"{measure}:{field.aggregator}"
            measures.append(measure)
        else:
            measures = ["__count", "__count"]

        locale = get_lang(self.env).code

        domain &= Domain(date_start, "!=", False)  # date not set are no take in account
        row_groups = self._read_group(
            domain=domain,
            groupby=[date_start + ":" + interval],
            aggregates=measures,
        )

        date_start_field = self._fields[date_start]
        if date_start_field.type == "datetime":
            today = datetime.today()
            convert_method = fields.Datetime.to_datetime
        else:
            today = date.today()
            convert_method = fields.Date.to_date

        for group_value, sum_value, value in row_groups:
            total_value += value
            group_domain = domain & Domain(
                [
                    "&",
                    (date_start, ">=", group_value),
                    (
                        date_start,
                        "<",
                        group_value + models.READ_GROUP_TIME_GRANULARITY[interval],
                    ),
                ]
            )
            sub_group = self._read_group(
                domain=group_domain,
                groupby=[date_stop + ":" + interval],
                aggregates=[measure],
            )
            sub_group_per_period = {
                convert_method(group_value): aggregate_value
                for group_value, aggregate_value in sub_group
            }

            columns = []
            initial_value = sum_value
            col_range = range(-15, 1) if timeline == "backward" else range(16)
            for col_index, col in enumerate(col_range):
                col_start_date = group_value
                if interval == "day":
                    col_start_date += relativedelta(days=col)
                    col_end_date = col_start_date + relativedelta(days=1)
                elif interval == "week":
                    col_start_date += relativedelta(days=7 * col)
                    col_end_date = col_start_date + relativedelta(days=7)
                elif interval == "month":
                    col_start_date += relativedelta(months=col)
                    col_end_date = col_start_date + relativedelta(months=1)
                elif interval == "quarter":
                    col_start_date += relativedelta(months=3 * col)
                    col_end_date = col_start_date + relativedelta(months=3)
                else:
                    col_start_date += relativedelta(years=col)
                    col_end_date = col_start_date + relativedelta(years=1)

                if col_start_date > today:
                    # ensure the key exists even for placeholder columns: the xlsx
                    # export controller indexes 0..columns_length-1 unconditionally
                    columns_avg.setdefault(col_index, {"percentage": 0, "count": 0})
                    columns.append(
                        {
                            "value": "-",
                            "churn_value": "-",
                            "percentage": "",
                        }
                    )
                    continue

                col_value = sub_group_per_period.get(col_start_date, 0.0)

                # In backward timeline, if columns are out of given range, we need
                # to set initial value for calculating correct percentage
                if timeline == "backward" and col_index == 0:
                    outside_timeline_domain = group_domain & (
                        Domain(date_stop, "=", False)
                        | Domain(
                            date_stop, ">=", fields.Datetime.to_string(col_start_date)
                        )
                    )
                    col_group = self._read_group(
                        domain=outside_timeline_domain,
                        aggregates=[measure],
                    )
                    initial_value = float(col_group[0][0])
                    initial_churn_value = sum_value - initial_value

                previous_col_remaining_value = (
                    initial_value if col_index == 0 else columns[-1]["value"]
                )
                col_remaining_value = previous_col_remaining_value - col_value
                percentage = (sum_value and (col_remaining_value) / sum_value) or 0
                if mode == "churn":
                    percentage = 1 - percentage

                percentage = round(100 * percentage, 1)

                columns_avg[col_index]["percentage"] += percentage
                columns_avg[col_index]["count"] += 1
                # For 'week' interval, we display a better tooltip (range like : '02 Jul - 08 Jul')
                if interval == "week":
                    period = "%s - %s" % (
                        format_date(self.env, col_start_date, date_format="dd MMM"),
                        format_date(
                            self.env,
                            col_end_date - relativedelta(days=1),
                            date_format="dd MMM",
                        ),
                    )
                elif interval == "quarter":
                    period = f"Q{date_utils.get_quarter_number(col_start_date)} {col_start_date.strftime('%Y')}"
                else:
                    period = format_date(
                        self.env, col_start_date, date_format=DISPLAY_FORMATS[interval]
                    )

                if mode == "churn":
                    mode_domain = [
                        (
                            date_stop,
                            "<",
                            col_end_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                        ),
                    ]
                else:
                    mode_domain = [
                        "|",
                        (
                            date_stop,
                            ">=",
                            col_end_date.strftime(DEFAULT_SERVER_DATE_FORMAT),
                        ),
                        (date_stop, "=", False),
                    ]

                columns.append(
                    {
                        "value": col_remaining_value,
                        "churn_value": col_value
                        + (
                            columns[-1]["churn_value"]
                            if col_index > 0
                            else initial_churn_value
                        ),
                        "percentage": percentage,
                        "domain": mode_domain,
                        "period": period,
                    }
                )

            rows.append(
                {
                    "date": babel.dates.format_date(
                        group_value,
                        format=models.READ_GROUP_DISPLAY_FORMAT[interval],
                        locale=locale,
                    ),
                    "value": value,
                    "domain": group_domain,
                    "columns": columns,
                }
            )

        return {
            "rows": rows,
            "avg": {
                "avg_value": total_value / len(rows) if rows else 0,
                "columns_avg": columns_avg,
            },
        }
