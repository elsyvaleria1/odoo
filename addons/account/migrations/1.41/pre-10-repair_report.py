def migrate(cr, version):
    if not version:
        return
    cr.execute("DROP TABLE IF EXISTS account_repair_141_report")
    cr.execute(
        """
        CREATE TABLE account_repair_141_report (
            id serial PRIMARY KEY,
            finding varchar NOT NULL,
            kind varchar NOT NULL,
            action varchar NOT NULL,
            model varchar,
            res_id integer,
            company_id integer,
            period varchar,
            amount numeric,
            detail varchar
        )
        """
    )
