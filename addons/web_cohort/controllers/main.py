import io

from werkzeug.datastructures import FileStorage

from odoo import http
from odoo.http import prepare_content_disposition_header, request
from odoo.libs.documents import mimetype_for
from odoo.libs.filesystem import osutil
from odoo.libs.json import loads as json_loads


class WebCohort(http.Controller):
    @http.route("/web/cohort/export", type="http", auth="user")
    def export_xls(self, data, **kw):
        result = json_loads(data.read()) if isinstance(data, FileStorage) else json_loads(data)

        output = io.BytesIO()
        import xlsxwriter

        with xlsxwriter.Workbook(output, {"in_memory": True}) as workbook:
            worksheet = workbook.add_worksheet(result["title"])
            style_highlight = workbook.add_format(
                {"bold": True, "pattern": 1, "bg_color": "#E0E0E0", "align": "center"}
            )
            style_normal = workbook.add_format({"align": "center"})
            row = 0

            def write_data(row, col):
                # Headers
                columns_length = len(result["report"]["rows"][0]["columns"])
                if result["timeline"] == "backward":
                    header_sign = ""
                    col_range = range(-(columns_length - 1), 1)
                else:
                    header_sign = "+"
                    col_range = range(columns_length)

                worksheet.merge_range(
                    row,
                    col + 2,
                    row,
                    columns_length + 1,
                    request.env._(
                        "%(date_stop)s - By %(interval)s",
                        date_stop=result["date_stop_string"],
                        interval=result["interval_string"],
                    ),
                    style_highlight,
                )
                row += 1
                worksheet.write(row, col, result["date_start_string"], style_highlight)
                col += 1
                worksheet.write(row, col, result["measure_string"], style_highlight)
                col += 1
                for n in col_range:
                    worksheet.write(
                        row, col, "%s%s" % (header_sign, n), style_highlight
                    )
                    col += 1

                # Rows
                row += 1
                for res in result["report"]["rows"]:
                    col = 0
                    worksheet.write(row, col, res["date"], style_normal)
                    col += 1
                    worksheet.write(row, col, res["value"], style_normal)
                    col += 1
                    for i in res["columns"]:
                        worksheet.write(
                            row,
                            col,
                            (i["percentage"] == "-" and i["percentage"])
                            or str(i["percentage"]) + "%",
                            style_normal,
                        )
                        col += 1
                    row += 1

                # Total
                col = 0
                worksheet.write(row, col, request.env._("Average"), style_highlight)
                col += 1
                worksheet.write(
                    row,
                    col,
                    "%.1f" % result["report"]["avg"]["avg_value"],
                    style_highlight,
                )
                col += 1
                total = result["report"]["avg"]["columns_avg"]
                for n in range(columns_length):
                    if total[str(n)]["count"]:
                        worksheet.write(
                            row,
                            col,
                            "%.1f"
                            % float(
                                total[str(n)]["percentage"] / total[str(n)]["count"]
                            )
                            + "%",
                            style_highlight,
                        )
                    else:
                        worksheet.write(row, col, "-", style_highlight)
                    col += 1

                return row

            row = write_data(row, 0)
            worksheet.autofit()

        xlsx_data = output.getvalue()
        filename = osutil.clean_filename(
            request.env._(
                "Cohort %(title)s (%(model_name)s)",
                title=result["title"],
                model_name=result["model"],
            )
        )
        return request.prepare_response(
            xlsx_data,
            headers=[
                (
                    "Content-Type",
                    mimetype_for("xlsx"),
                ),
                (
                    "Content-Disposition",
                    prepare_content_disposition_header(filename + ".xlsx"),
                ),
            ],
        )
