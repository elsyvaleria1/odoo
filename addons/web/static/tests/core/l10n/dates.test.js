// @ts-check

import { beforeEach, expect, test } from "@odoo/hoot";
import { mockDate, mockTimeZone } from "@odoo/hoot-mock";
import {
    allowTranslations,
    defineParams,
    makeMockEnv,
    patchWithCleanup,
} from "@web/../tests/web_test_helpers";
import {
    dateSettings,
    dateTime,
    deserializeDate,
    deserializeDateTime,
    formatDate,
    formatDateTime,
    formatDuration,
    formatValue,
    now,
    parseDate as parseDateOrNull,
    parseDateTime as parseDateTimeOrNull,
    parseFormatted,
    parseISO,
    serializeDate,
    serializeDateTime,
    strftimeToDateFormat,
    toISO,
    toISODate,
    toLocaleDateTimeString,
} from "@web/core/l10n/dates";
import { localization } from "@web/core/l10n/localization";

const parseDate =
    /** @type {(...args: Parameters<typeof parseDateOrNull>) => Temporal.PlainDate} */ (
        parseDateOrNull
    );
const parseDateTime =
    /** @type {(...args: Parameters<typeof parseDateTimeOrNull>) => Temporal.ZonedDateTime} */ (
        parseDateTimeOrNull
    );

const formats = {
    date: "%d.%m/%Y",
    time: "%H:%M:%S",
};
const dateFormat = strftimeToDateFormat(formats.date);
const timeFormat = strftimeToDateFormat(formats.time);

beforeEach(() => {
    allowTranslations();
});

test("formatDate/formatDateTime specs", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockDate("2009-05-04 11:34:56", +1);

    const utc = now("UTC");
    const local = now();
    const minus13FromLocalTZ = local.withTimeZone("-12:00");

    expect(formatDate(utc)).toBe("05/04/2009");
    expect(formatDate(local)).toBe("05/04/2009");
    expect(formatDate(minus13FromLocalTZ)).toBe("05/03/2009");

    expect(formatDateTime(utc)).toBe("05/04/2009 12:34:56");
    expect(formatDateTime(local)).toBe("05/04/2009 12:34:56");
    expect(formatDateTime(minus13FromLocalTZ)).toBe("05/04/2009 12:34:56");
});

test("strftimeToDateFormat: %j is the zero-padded 3-digit day of year", () => {
    const dateFormatJ = strftimeToDateFormat("%j");
    expect(formatValue(dateTime({ year: 2024, month: 1, day: 1 }), dateFormatJ)).toBe(
        "001",
    );
    expect(formatValue(dateTime({ year: 2024, month: 3, day: 5 }), dateFormatJ)).toBe(
        "065",
    );
    expect(formatValue(dateTime({ year: 2024, month: 12, day: 31 }), dateFormatJ)).toBe(
        "366",
    );
});

test("strftimeToDateFormat: weekday and week-of-year numbers have no date token", () => {
    expect(strftimeToDateFormat("%w")).toBe("'w'");
    expect(strftimeToDateFormat("%W")).toBe("'W'");
    expect(strftimeToDateFormat("%U")).toBe("'U'");
    const sunday = dateTime({ year: 2023, month: 1, day: 1 });
    expect(formatValue(sunday, strftimeToDateFormat("%Y %w %W"))).toBe("2023 w W");
});

test("formatDate/formatDateTime specs, at midnight", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockDate("2009-05-03 23:00:00", +1);

    const utc = now("UTC");
    const local = now();
    const minus13FromLocalTZ = local.withTimeZone("-12:00");

    expect(formatDate(utc)).toBe("05/03/2009");
    expect(formatDate(local)).toBe("05/04/2009");
    expect(formatDate(minus13FromLocalTZ)).toBe("05/03/2009");

    expect(formatDateTime(utc)).toBe("05/04/2009 00:00:00");
    expect(formatDateTime(local)).toBe("05/04/2009 00:00:00");
    expect(formatDateTime(minus13FromLocalTZ)).toBe("05/04/2009 00:00:00");
});

test("formatDateTime in different timezone", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockDate("2009-05-04 00:00:00", 0);
    expect(formatDateTime(now("UTC"))).toBe("05/04/2009 00:00:00");
    expect(formatDateTime(now("UTC"), { tz: "Asia/Kolkata" })).toBe(
        "05/04/2009 05:30:00",
    );
});

test("parseDate outputs the day in any TZ, parseDateTime the instant in local TZ", async () => {
    await makeMockEnv();
    mockTimeZone(+1);
    expect(toISO(parseDate("01/13/2019"))).toBe("2019-01-13");
    expect(toISO(parseDateTime("01/13/2019 10:05:45"))).toBe(
        "2019-01-13T10:05:45.000+01:00",
    );

    mockTimeZone(+5.5);
    expect(toISO(parseDate("01/13/2019"))).toBe("2019-01-13");
    expect(toISO(parseDateTime("01/13/2019 10:05:45"))).toBe(
        "2019-01-13T10:05:45.000+05:30",
    );

    mockTimeZone(-11);
    expect(toISO(parseDate("01/13/2019"))).toBe("2019-01-13");
    expect(toISO(parseDateTime("01/13/2019 10:05:45"))).toBe(
        "2019-01-13T10:05:45.000-11:00",
    );
});

test("parseDateTime in different timezone", async () => {
    await makeMockEnv();
    mockTimeZone(+1);
    expect(toISO(parseDateTime("01/13/2019 10:05:45"))).toBe(
        "2019-01-13T10:05:45.000+01:00",
    );
    expect(toISO(parseDateTime("01/13/2019 10:05:45", { tz: "Asia/Kolkata" }))).toBe(
        "2019-01-13T10:05:45.000+05:30",
    );
});

test("an unknown tz formats, parses and deserializes in the default zone, warning once", async () => {
    await makeMockEnv();
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockTimeZone(+2);
    /** @type {string[]} */
    const warnings = [];
    patchWithCleanup(console, { warn: (message) => warnings.push(message) });
    const tz = "Mars/Valles_Marineris";
    const instant = parseISO("2009-05-04T00:00:00Z");

    expect(formatDateTime(instant, { tz })).toBe("05/04/2009 02:00:00");
    expect(toLocaleDateTimeString(instant, { tz })).toMatch(/^May 4, 2009, 2:00\sAM$/);
    expect(toISO(parseDateTime("01/13/2019 10:05:45", { tz }))).toBe(
        "2019-01-13T10:05:45.000+02:00",
    );
    expect(toISO(deserializeDateTime("2019-01-13 08:05:45", { tz }))).toBe(
        "2019-01-13T10:05:45.000+02:00",
    );
    expect(warnings.filter((warning) => warning.includes(tz))).toHaveLength(1);
});

test("parseDate with different numbering system", async () => {
    patchWithCleanup(localization, {
        dateFormat: "dd MMM, yyyy",
        dateTimeFormat: "dd MMM, yyyy hh:mm:ss",
        timeFormat: "hh:mm:ss",
    });

    patchWithCleanup(dateSettings, { numberingSystem: "arab", locale: "ar" });

    expect(toISO(parseDate("٠١ فبراير, ٢٠٢٣"))).toBe("2023-02-01");
});

test("formatDuration respects the unit count in an 'and'-joined locale", async () => {
    patchWithCleanup(dateSettings, { locale: "ar" });

    const twoHoursThreeMinutes = 2 * 3600 + 3 * 60;
    expect(formatDuration(twoHoursThreeMinutes, false)).toBe("2 س");
    expect(formatDuration(twoHoursThreeMinutes, false)).toBe(
        formatDuration(2 * 3600, false),
    );
    expect(formatDuration(twoHoursThreeMinutes, true)).toBe("ساعتان, 3 دقائق");

    const threeDaysPlus = 3 * 86400 + 5 * 3600 + 9 * 60;
    expect(formatDuration(threeDaysPlus, false)).toBe("3 ي");
});

test("formatDuration handles zero, sub-minute and negative durations", async () => {
    patchWithCleanup(dateSettings, { locale: "en" });

    expect(formatDuration(0, false)).toBe("0m");
    expect(formatDuration(30, false)).toBe("0m");
    expect(formatDuration(-90, false)).toBe("-1m");
    expect(formatDuration(-90, true)).toBe("-1 minute");
    expect(formatDuration(2 * 3600 + 3 * 60, false)).toBe("2h");
    expect(formatDuration(2 * 3600 + 3 * 60, true)).toBe("2 hours, 3 minutes");
    expect(formatDuration(40 * 86400 + 3 * 3600, false)).toBe("1M");
});

test("parseDateTime", async () => {
    expect(() => parseDateTime("13/01/2019 12:00:00")).toThrow(/is not a correct/, {
        message: "Wrongly formated dates should be invalid",
    });
    expect(() => parseDateTime("01/01/0999 12:00:00")).toThrow(/is not a correct/, {
        message: "Dates before 1000 should be invalid",
    });
    expect(() => parseDateTime("01/01/10000 12:00:00")).toThrow(/is not a correct/, {
        message: "Dates after 9999 should be invalid",
    });
    expect(() => parseDateTime("invalid value")).toThrow(/is not a correct/);

    const expected = "2019-01-13T10:05:45.000+01:00";
    expect(toISO(parseDateTime("01/13/2019 10:05:45"))).toBe(expected, {
        message: "Date with leading 0",
    });
    expect(toISO(parseDateTime("1/13/2019 10:5:45"))).toBe(expected, {
        message: "Date without leading 0",
    });
});

test("parseDateTime (norwegian locale)", async () => {
    defineParams({
        lang: "no",
        lang_parameters: {
            date_format: "%d. %b %Y",
            time_format: "%H:%M:%S",
        },
    });
    await makeMockEnv();

    expect(toISO(parseDateTime("16. des 2019 10:05:45"))).toBe(
        "2019-12-16T10:05:45.000+01:00",
        {
            message: "Day/month inverted + month i18n",
        },
    );
});

test("parseDate", async () => {
    await makeMockEnv();
    expect(toISO(parseDate("07/21/2022"))).toBe("2022-07-21");
    expect(toISO(parseDate("07/22/2022"))).toBe("2022-07-22");
});

test("parseDate without separator", async () => {
    const dateFormat = strftimeToDateFormat("%d.%m/%Y");
    const timeFormat = strftimeToDateFormat("%H:%M:%S");
    patchWithCleanup(localization, {
        dateFormat,
        timeFormat,
        dateTimeFormat: `${dateFormat} ${timeFormat}`,
    });

    const testDateFormat = "dd.MM/yyyy";

    expect(() => parseDate("1137")).toThrow(/is not a correct/, {
        message: "Wrongly formated dates should be invalid",
    });
    expect(() => parseDate("1197")).toThrow(/is not a correct/, {
        message: "Wrongly formated dates should be invalid",
    });
    expect(() => parseDate("0131")).toThrow(/is not a correct/, {
        message: "Wrongly formated dates should be invalid",
    });
    expect(() => parseDate("970131")).toThrow(/is not a correct/, {
        message: "Wrongly formated dates should be invalid",
    });
    expect(formatValue(parseDate("2001"), testDateFormat)).toBe(
        "20.01/" + now("UTC").year,
    );
    expect(formatValue(parseDate("3101"), testDateFormat)).toBe(
        "31.01/" + now("UTC").year,
    );
    expect(formatValue(parseDate("31.01"), testDateFormat)).toBe(
        "31.01/" + now("UTC").year,
    );
    expect(formatValue(parseDate("310197"), testDateFormat)).toBe("31.01/1997");
    expect(formatValue(parseDate("310117"), testDateFormat)).toBe("31.01/2017");
    expect(formatValue(parseDate("31011985"), testDateFormat)).toBe("31.01/1985");
});

test("parseDateTime without separator", async () => {
    const dateFormat = strftimeToDateFormat("%d.%m/%Y");
    const timeFormat = strftimeToDateFormat("%H:%M:%S");
    patchWithCleanup(localization, {
        dateFormat,
        timeFormat,
        dateTimeFormat: `${dateFormat} ${timeFormat}`,
    });

    const dateTimeFormat = "dd.MM/yyyy HH:mm/ss";
    expect(formatValue(parseDateTime("3101198508"), dateTimeFormat)).toBe(
        "31.01/1985 08:00/00",
    );
    expect(formatValue(parseDateTime("310119850833"), dateTimeFormat)).toBe(
        "31.01/1985 08:33/00",
    );
    expect(formatValue(parseDateTime("31/01/1985 08"), dateTimeFormat)).toBe(
        "31.01/1985 08:00/00",
    );
});

test("parseDateTime with escaped characters (eg. Basque locale)", async () => {
    const dateFormat = strftimeToDateFormat("%a, %Y.eko %bren %da");
    const timeFormat = strftimeToDateFormat("%H:%M:%S");
    patchWithCleanup(localization, {
        dateFormat,
        timeFormat,
        dateTimeFormat: `${dateFormat} ${timeFormat}`,
    });

    const dateTimeFormat = `${dateFormat} ${timeFormat}`;
    expect(dateTimeFormat).toBe("ccc, yyyy.'e''k''o' MMM'r''e''n' dd'a' HH:mm:ss");
    expect(formatValue(parseDateTime("1985-01-31 08:30:00"), dateTimeFormat)).toBe(
        "Thu, 1985.eko Janren 31a 08:30:00",
    );
});

test("parse smart date input", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
        weekStart: 1,
    });
    mockDate("2020-01-01 00:00:00", 0);

    const format = "yyyy-MM-dd HH:mm";
    expect(formatValue(parseDate("+0"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDate("-0"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDate("+1d"), format)).toBe("2020-01-02 00:00");
    expect(formatValue(parseDate("+2w"), format)).toBe("2020-01-15 00:00");
    expect(formatValue(parseDate("+3m"), format)).toBe("2020-04-01 00:00");
    expect(formatValue(parseDate("+4y"), format)).toBe("2024-01-01 00:00");
    expect(formatValue(parseDate("+5"), format)).toBe("2020-01-06 00:00");
    expect(formatValue(parseDate("-5"), format)).toBe("2019-12-27 00:00");
    expect(formatValue(parseDate("-4y"), format)).toBe("2016-01-01 00:00");
    expect(formatValue(parseDate("-3m"), format)).toBe("2019-10-01 00:00");
    expect(formatValue(parseDate("-2w"), format)).toBe("2019-12-18 00:00");
    expect(formatValue(parseDate("-1d"), format)).toBe("2019-12-31 00:00");
    expect(formatValue(parseDateTime("+0"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDateTime("-0"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDateTime("+1d"), format)).toBe("2020-01-02 00:00");
    expect(formatValue(parseDateTime("+2w"), format)).toBe("2020-01-15 00:00");
    expect(formatValue(parseDateTime("+3m"), format)).toBe("2020-04-01 00:00");
    expect(formatValue(parseDateTime("+4y"), format)).toBe("2024-01-01 00:00");
    expect(formatValue(parseDateTime("+5"), format)).toBe("2020-01-06 00:00");
    expect(formatValue(parseDateTime("-5"), format)).toBe("2019-12-27 00:00");
    expect(formatValue(parseDateTime("-4y"), format)).toBe("2016-01-01 00:00");
    expect(formatValue(parseDateTime("-3m"), format)).toBe("2019-10-01 00:00");
    expect(formatValue(parseDateTime("-2w"), format)).toBe("2019-12-18 00:00");
    expect(formatValue(parseDateTime("-1d"), format)).toBe("2019-12-31 00:00");

    mockDate("2020-01-01 00:01:00", 0);

    expect(formatValue(parseDateTime("=3d"), format)).toBe("2020-01-03 00:00");
    expect(formatValue(parseDateTime("+3d +1m"), format)).toBe("2020-02-04 00:01");
    expect(formatValue(parseDateTime("=11d +2H +15M"), format)).toBe(
        "2020-01-11 02:15",
    );
    expect(formatValue(parseDateTime("=11d =3H +2H +15M"), format)).toBe(
        "2020-01-11 05:15",
    );

    expect(formatValue(parseDateTime("now"), format)).toBe("2020-01-01 00:01");
    expect(formatValue(parseDateTime("today"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDateTime("today +1w"), format)).toBe("2020-01-08 00:00");

    expect(formatValue(parseDateTime("=monday"), format)).toBe("2019-12-30 00:00");
    expect(formatValue(parseDateTime("=sunday"), format)).toBe("2020-01-05 00:00");
    expect(formatValue(parseDateTime("+monday"), format)).toBe("2020-01-06 00:01");

    expect(formatValue(parseDateTime("=3H =11d"), format)).toBe("2020-01-11 00:00");
    expect(formatValue(parseDateTime("=3H =sunday"), format)).toBe("2020-01-05 00:00");

    expect(formatValue(parseDateTime("=week_start"), format)).toBe("2019-12-30 00:00");
    expect(formatValue(parseDateTime("-week_start"), format)).toBe("2019-12-30 00:01");
    expect(formatValue(parseDateTime("+week_start"), format)).toBe("2020-01-06 00:01");

    patchWithCleanup(localization, { weekStart: 7 });
    expect(formatValue(parseDateTime("=week_start"), format)).toBe("2019-12-29 00:00");
    expect(formatValue(parseDateTime("-week_start"), format)).toBe("2019-12-29 00:01");
    expect(formatValue(parseDateTime("+week_start"), format)).toBe("2020-01-05 00:01");
    expect(formatValue(parseDateTime("=sunday"), format)).toBe("2019-12-29 00:00");

    patchWithCleanup(localization, { weekStart: 3 });
    expect(formatValue(parseDateTime("=week_start"), format)).toBe("2020-01-01 00:00");
    expect(formatValue(parseDateTime("-week_start"), format)).toBe("2020-01-01 00:01");
    expect(formatValue(parseDateTime("+week_start"), format)).toBe("2020-01-01 00:01");
    expect(formatValue(parseDateTime("=tuesday"), format)).toBe("2020-01-07 00:00");
    expect(formatValue(parseDateTime("=wednesday"), format)).toBe("2020-01-01 00:00");
});

test("smart date input reads today and now in the tz it is given, not the browser's", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockDate("2020-01-01 10:00:00", +9);
    const tz = "America/Los_Angeles";

    expect(toISO(parseDateTime("today", { tz }))).toBe(
        "2020-01-01T00:00:00.000-08:00",
        {
            message: "19:00 in Tokyo, 02:00 in Los Angeles: both on January 1st",
        },
    );
    expect(toISO(parseDateTime("now", { tz }))).toBe("2020-01-01T02:00:00.000-08:00");
    expect(toISODate(parseDate("today", { tz }))).toBe("2020-01-01");
    expect(toISODate(parseDate("+1d", { tz }))).toBe("2020-01-02");
});

test("smart date input sets a day, month or year within the month, as relativedelta does", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MM/dd/yyyy",
        dateTimeFormat: "MM/dd/yyyy HH:mm:ss",
    });
    mockDate("2026-02-10 10:00:00", 0);
    expect(toISODate(parseDate("=31d"))).toBe("2026-02-28");
    expect(toISODate(parseDate("=29"))).toBe("2026-02-28");
    expect(toISODate(parseDate("=15"))).toBe("2026-02-15");
    expect(formatValue(parseDateTime("=31d +2H"), "yyyy-MM-dd HH:mm")).toBe(
        "2026-02-28 02:00",
    );

    mockDate("2026-01-31 10:00:00", 0);
    expect(toISODate(parseDate("=2m"))).toBe("2026-02-28");
    expect(toISODate(parseDate("=3m"))).toBe("2026-03-31");

    mockDate("2024-02-29 10:00:00", 0);
    expect(toISODate(parseDate("=2025y"))).toBe("2025-02-28");
    expect(toISODate(parseDate("=2028y"))).toBe("2028-02-29");
});

test("parseDateTime ISO8601 Format", async () => {
    mockTimeZone(+1);
    expect(toISO(parseDateTime("2017-05-15T12:00:00.000+06:00"))).toBe(
        "2017-05-15T07:00:00.000+01:00",
    );
    expect(toISO(parseDateTime("2017-05-15 12:00:00.000+06:00"))).toBe(
        "2017-05-15T07:00:00.000+01:00",
    );
});

test("parseDateTime SQL Format", async () => {
    expect(toISO(parseDateTime("2017-05-15 09:12:34"))).toBe(
        "2017-05-15T09:12:34.000+01:00",
    );
    expect(toISO(parseDateTime("2017-05-08 09:12:34"))).toBe(
        "2017-05-08T09:12:34.000+01:00",
    );
});

test("serializeDate", async () => {
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(formatValue(date, "yyyy-MM-dd")).toBe("2022-02-21");
    expect(serializeDate(date)).toBe("2022-02-21");
});

test("serializeDate, with now()", async () => {
    mockDate("2022-02-21 15:11:42");
    const date = now();
    expect(formatValue(date, "yyyy-MM-dd")).toBe("2022-02-21");
    expect(serializeDate(date)).toBe("2022-02-21");
});

test("serializeDate, with now(), midnight", async () => {
    mockDate("2022-02-20 23:00:00");
    const date = now();
    expect(formatValue(date, "yyyy-MM-dd")).toBe("2022-02-21");
    expect(serializeDate(date)).toBe("2022-02-21");
});

test("serializeDate with different numbering system", async () => {
    patchWithCleanup(dateSettings, { numberingSystem: "arab" });
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(formatValue(date, "yyyy-MM-dd")).toBe("٢٠٢٢-٠٢-٢١");
    expect(serializeDate(date)).toBe("2022-02-21");
});

test("serializeDateTime", async () => {
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(formatValue(date, "yyyy-MM-dd HH:mm:ss")).toBe("2022-02-21 16:11:42");
    expect(serializeDateTime(date)).toBe("2022-02-21 16:11:42");
});

test("serializeDateTime, with now()", async () => {
    mockDate("2022-02-21 15:11:42");
    const date = now();
    expect(formatValue(date, "yyyy-MM-dd HH:mm:ss")).toBe("2022-02-21 16:11:42");
    expect(serializeDateTime(date)).toBe("2022-02-21 15:11:42");
});

test("serializeDateTime, with now(), midnight", async () => {
    mockDate("2022-02-20 23:00:00");
    const date = now();
    expect(formatValue(date, "yyyy-MM-dd HH:mm:ss")).toBe("2022-02-21 00:00:00");
    expect(serializeDateTime(date)).toBe("2022-02-20 23:00:00");
});

test("serializeDateTime with different numbering system", async () => {
    patchWithCleanup(dateSettings, { numberingSystem: "arab" });
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(formatValue(date, "yyyy-MM-dd HH:mm:ss")).toBe("٢٠٢٢-٠٢-٢١ ١٦:١١:٤٢");
    expect(serializeDateTime(date)).toBe("2022-02-21 16:11:42");
});

test("deserializeDate", async () => {
    const date = dateTime({ year: 2022, month: 2, day: 21 });
    expect(parseFormatted("2022-02-21", "yyyy-MM-dd").epochMilliseconds).toBe(
        date.epochMilliseconds,
    );
    expect(deserializeDate("2022-02-21")).toBeInstanceOf(Temporal.PlainDate);
    expect(deserializeDate("2022-02-21").toString()).toBe("2022-02-21");
});

test("deserializeDate is the same day in every time zone", async () => {
    for (const offset of [-11, 0, +5.5, +13]) {
        mockTimeZone(offset);
        expect(serializeDate(deserializeDate("2022-02-21"))).toBe("2022-02-21");
        expect(formatDate(deserializeDate("2022-02-21"), { format: "dd" })).toBe("21");
    }
});

test("deserializeDate drops a time, as a date has none", async () => {
    expect(deserializeDate("2022-02-21 23:30:00").toString()).toBe("2022-02-21");
});

test("deserializeDate with different numbering system", async () => {
    patchWithCleanup(dateSettings, { numberingSystem: "arab" });
    const date = dateTime({ year: 2022, month: 2, day: 21 });
    expect(parseFormatted("٢٠٢٢-٠٢-٢١", "yyyy-MM-dd").epochMilliseconds).toBe(
        date.epochMilliseconds,
    );
    expect(deserializeDate("2022-02-21").toString()).toBe("2022-02-21");
});

test("serializeDate of a date is its day", async () => {
    expect(serializeDate(Temporal.PlainDate.from("2022-02-21"))).toBe("2022-02-21");
});

test("deserializeDateTime", async () => {
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(
        parseFormatted("2022-02-21 16:11:42", "yyyy-MM-dd HH:mm:ss", "UTC")
            .epochMilliseconds,
    ).toBe(date.epochMilliseconds);
    expect(deserializeDateTime("2022-02-21 16:11:42").epochMilliseconds).toBe(
        date.epochMilliseconds,
    );
});

test("deserializeDateTime with different numbering system", async () => {
    patchWithCleanup(dateSettings, { numberingSystem: "arab" });
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    );
    expect(
        parseFormatted("٢٠٢٢-٠٢-٢١ ١٦:١١:٤٢", "yyyy-MM-dd HH:mm:ss", "UTC")
            .epochMilliseconds,
    ).toBe(date.epochMilliseconds);
    expect(deserializeDateTime("2022-02-21 16:11:42").epochMilliseconds).toBe(
        date.epochMilliseconds,
    );
});

test("deserializeDateTime with different timezone", async () => {
    const date = dateTime(
        { year: 2022, month: 2, day: 21, hour: 16, minute: 11, second: 42 },
        "UTC",
    ).withTimeZone("Europe/Brussels");
    expect(
        deserializeDateTime("2022-02-21 16:11:42", {
            tz: "Europe/Brussels",
        }).toPlainDateTime(),
    ).toEqual(date.toPlainDateTime());
});

test("parseDate with short notations", async () => {
    expect(toISO(parseDate("20-10-20", { format: "yyyy-MM-dd" }))).toBe("2020-10-20");
    expect(toISO(parseDate("20/10/20", { format: "yyyy/MM/dd" }))).toBe("2020-10-20");
    expect(toISO(parseDate("10-20-20", { format: "MM-dd-yyyy" }))).toBe("2020-10-20");
    expect(toISO(parseDate("10-20-20", { format: "MM-yyyy-dd" }))).toBe("2020-10-20");
    expect(toISO(parseDate("1-20-2", { format: "MM-yyyy-dd" }))).toBe("2020-01-02");
    expect(toISO(parseDate("20/1/2", { format: "yyyy/MM/dd" }))).toBe("2020-01-02");
});

test("parseDateTime with short notations", async () => {
    expect(
        toISO(parseDateTime("20-10-20 8:5:3", { format: "yyyy-MM-dd hh:mm:ss" })),
    ).toBe("2020-10-20T08:05:03.000+01:00");
});

test("parseDate with textual month notation", async () => {
    patchWithCleanup(localization, {
        dateFormat: "MMM/dd/yyyy",
    });
    expect(toISO(parseDate("Jan/05/1997"))).toBe("1997-01-05");
    expect(toISO(parseDate("Jan/05/1997", { format: undefined }))).toBe("1997-01-05");
    expect(toISO(parseDate("Jan/05/1997", { format: "MMM/dd/yyyy" }))).toBe(
        "1997-01-05",
    );
});

test("parseDate (various entries)", async () => {
    mockDate("2020-07-15 12:30:00", 0);
    patchWithCleanup(localization, {
        dateFormat,
        timeFormat,
        dateTimeFormat: `${dateFormat} ${timeFormat}`,
    });

    const testSet = new Map([
        ["10101010101010", undefined],
        ["1191111", "1191-04-21"],
        ["11911111", "1191-11-11"],
        ["3101", "2020-01-31"],
        ["310160", "2060-01-31"],
        ["311260", "2060-12-31"],

        ["310161", "1961-01-31"],
        ["310165", "1965-01-31"],
        ["310168", "1968-01-31"],
        ["311268", "1968-12-31"],

        ["310169", "1969-01-31"],
        ["310170", "1970-01-31"],
        ["310197", "1997-01-31"],
        ["310117", "2017-01-31"],
        ["31011985", "1985-01-31"],
        ["3101198508", undefined],
        ["310119850833", undefined],

        ["1137", undefined],
        ["1197", undefined],
        ["0131", undefined],
        ["0922", undefined],
        ["2020", undefined],

        ["199901", "1999-01-01"],
        ["30100210", "3010-02-10"],
        ["3010210", "3010-07-29"],

        ["970131", undefined],
        ["31.01", "2020-01-31"],
        ["31/01/1985 08", undefined],

        ["01121934", "1934-12-01"],
        ["011234", "2034-12-01"],
        ["011260", "2060-12-01"],
        ["2", "2020-07-02"],
        ["02", "2020-07-02"],
        ["20", "2020-07-20"],
        ["202", "2020-02-20"],
        ["2002", "2020-02-20"],
        ["0202", "2020-02-02"],
        ["02/02", "2020-02-02"],
        ["02/13", undefined],
        ["02/1313", undefined],
        ["09990101", undefined],
        ["19990101", "1999-01-01"],
        ["19990130", "1999-01-30"],
        ["19991230", "1999-12-30"],
        ["19993012", undefined],
        ["2016-200", "2016-07-18"],
        ["2016200", "2016-07-18"],
        ["2020-", undefined],
        ["2020-W2", undefined],
        ["2020W23", "2020-06-01"],
        ["2020-W02", "2020-01-06"],
        ["2020-W32", "2020-08-03"],
        ["2020-W32-3", "2020-08-05"],
        ["2016-W21-3", "2016-05-25"],
        ["2016W213", "2016-05-25"],
        ["2209", "2020-09-22"],
        ["22:09", "2020-09-22"],
        ["2012", "2020-12-20"],

        ["2016-01-03 09:24:15.123", "2016-01-03"],
        ["2016-01-03T09:24:15.123", "2016-01-03"],
        ["2016-01-03T09:24:15.123+06:00", "2016-01-03"],
        ["2016-01-03T09:24:15.123+16:00", "2016-01-02"],
        ["2016-01-03T09:24:15.123Z", "2016-01-03"],
        ["2016-W21-3T09:24:15.123", "2016-05-25"],
        ["2016-W21-3 09:24:15.123", undefined],

        ["2016-03-27T02:00:00.000+02:00", "2016-03-27"],
        ["2016-03-27T03:00:00.000+02:00", "2016-03-27"],
        ["2016-03-27T02:00:00.000", "2016-03-27"],
        ["2016-03-27T03:00:00.000", "2016-03-27"],
        ["2016-03-27T02:00:00.000Z", "2016-03-27"],
        ["2016-03-27T03:00:00.000Z", "2016-03-27"],

        ["09:22", undefined],
        ["2013", undefined],
        ["011261", "1961-12-01"],

        ["932-10-10", undefined],
        ["1932-10-10", "1932-10-10"],
        ["2016-01-03 09:24:15.123+06:00", "2016-01-03"],
        ["2016-01-03 09:24:15.123+16:00", "2016-01-02"],
        ["2016-01-03 09:24:15.123Z", "2016-01-03"],
    ]);

    for (const [input, expected] of testSet.entries()) {
        if (!expected) {
            expect(() => toISO(parseDate(input))).toThrow(/is not a correct/);
        } else {
            expect(toISO(parseDate(input))).toBe(expected);
        }
    }
});

test("parseDateTime (various entries)", async () => {
    mockDate("2020-07-15 11:30:00", 0);
    patchWithCleanup(localization, {
        dateFormat,
        timeFormat,
        dateTimeFormat: `${dateFormat} ${timeFormat}`,
    });

    const testSet = new Map([
        ["10101010101010", "1010-10-10T10:10:10.000Z"],
        ["1191111", "1191-04-21T00:00:00.000Z"],
        ["11911111", "1191-11-11T00:00:00.000Z"],
        ["3101", "2020-01-31T00:00:00.000Z"],
        ["310160", "2060-01-31T00:00:00.000Z"],
        ["311260", "2060-12-31T00:00:00.000Z"],
        ["310161", "1961-01-31T00:00:00.000Z"],
        ["310165", "1965-01-31T00:00:00.000Z"],
        ["310168", "1968-01-31T00:00:00.000Z"],
        ["311268", "1968-12-31T00:00:00.000Z"],
        ["310169", "1969-01-31T00:00:00.000Z"],
        ["310170", "1970-01-31T00:00:00.000Z"],
        ["310197", "1997-01-31T00:00:00.000Z"],
        ["310117", "2017-01-31T00:00:00.000Z"],
        ["31011985", "1985-01-31T00:00:00.000Z"],
        ["3101198508", "1985-01-31T08:00:00.000Z"],
        ["310119850833", "1985-01-31T08:33:00.000Z"],
        ["1137", undefined],
        ["1197", undefined],
        ["0131", undefined],
        ["0922", undefined],
        ["2020", undefined],
        ["199901", "1999-01-01T00:00:00.000Z"],
        ["30100210", "3010-02-10T00:00:00.000Z"],
        ["3010210", "3010-07-29T00:00:00.000Z"],
        ["970131", undefined],
        ["31.01", "2020-01-31T00:00:00.000Z"],
        ["31/01/1985 08", "1985-01-31T08:00:00.000Z"],

        ["01121934", "1934-12-01T00:00:00.000Z"],
        ["011234", "2034-12-01T00:00:00.000Z"],
        ["011260", "2060-12-01T00:00:00.000Z"],
        ["2", "2020-07-02T00:00:00.000Z"],
        ["02", "2020-07-02T00:00:00.000Z"],
        ["20", "2020-07-20T00:00:00.000Z"],
        ["202", "2020-02-20T00:00:00.000Z"],
        ["2002", "2020-02-20T00:00:00.000Z"],
        ["0202", "2020-02-02T00:00:00.000Z"],
        ["02/02", "2020-02-02T00:00:00.000Z"],
        ["02/13", undefined],
        ["02/1313", undefined],
        ["09990101", undefined],
        ["19990101", "1999-01-01T00:00:00.000Z"],
        ["19990130", "1999-01-30T00:00:00.000Z"],
        ["19991230", "1999-12-30T00:00:00.000Z"],
        ["19993012", undefined],
        ["2016-200", "2016-07-18T00:00:00.000Z"],
        ["2016200", "2016-07-18T00:00:00.000Z"],
        ["2020-", undefined],
        ["2020-W2", undefined],
        ["2020W23", "2020-06-01T00:00:00.000Z"],
        ["2020-W02", "2020-01-06T00:00:00.000Z"],
        ["2020-W32", "2020-08-03T00:00:00.000Z"],
        ["2020-W32-3", "2020-08-05T00:00:00.000Z"],
        ["2016-W21-3", "2016-05-25T00:00:00.000Z"],
        ["2016W213", "2016-05-25T00:00:00.000Z"],
        ["2209", "2020-09-22T00:00:00.000Z"],
        ["22:09", "2020-09-22T00:00:00.000Z"],
        ["2012", "2020-12-20T00:00:00.000Z"],

        ["2016-01-03 09:24:15.123", "2016-01-03T09:24:15.123Z"],
        ["2016-01-03T09:24:15.123", "2016-01-03T09:24:15.123Z"],
        ["2016-01-03T09:24:15.123+06:00", "2016-01-03T03:24:15.123Z"],
        ["2016-01-03T09:24:15.123+16:00", "2016-01-02T17:24:15.123Z"],
        ["2016-01-03T09:24:15.123Z", "2016-01-03T09:24:15.123Z"],
        ["2016-W21-3T09:24:15.123", "2016-05-25T09:24:15.123Z"],
        ["2016-W21-3 09:24:15.123", undefined],

        ["2016-03-27T02:00:00.000+02:00", "2016-03-27T00:00:00.000Z"],
        ["2016-03-27T03:00:00.000+02:00", "2016-03-27T01:00:00.000Z"],
        ["2016-03-27T02:00:00.000", "2016-03-27T02:00:00.000Z"],
        ["2016-03-27T03:00:00.000", "2016-03-27T03:00:00.000Z"],
        ["2016-03-27T02:00:00.000Z", "2016-03-27T02:00:00.000Z"],
        ["2016-03-27T03:00:00.000Z", "2016-03-27T03:00:00.000Z"],

        ["09:22", undefined],
        ["2013", undefined],
        ["011261", "1961-12-01T00:00:00.000Z"],

        ["932-10-10", undefined],
        ["1932-10-10", "1932-10-10T00:00:00.000Z"],
        ["2016-01-03 09:24:15.123+06:00", "2016-01-03T03:24:15.123Z"],
        ["2016-01-03 09:24:15.123+16:00", "2016-01-02T17:24:15.123Z"],
        ["2016-01-03 09:24:15.123Z", "2016-01-03T09:24:15.123Z"],
    ]);

    for (const [input, expected] of testSet.entries()) {
        if (!expected) {
            expect(() => toISO(parseDateTime(input))).toThrow(/is not a correct/);
        } else {
            expect(toISO(parseDateTime(input))).toBe(expected);
        }
    }
});

test("parseDateTime: arab locale, latin numbering system as input", async () => {
    defineParams({
        lang: "ar_001",
        lang_parameters: {
            date_format: "%d %b, %Y",
            time_format: "%H:%M:%S",
        },
    });
    await makeMockEnv();

    expect(toISO(parseDateTime("١٥ يوليو, ٢٠٢٠ ١٢:٣٠:٤٣")).split(".")[0]).toBe(
        "2020-07-15T12:30:43",
    );

    expect(toISO(parseDateTime("15 07, 2020 12:30:43")).split(".")[0]).toBe(
        "2020-07-15T12:30:43",
    );
    expect(toISO(parseDateTime("22/01/2023")).split(".")[0]).toBe(
        "2023-01-22T00:00:00",
    );
    expect(toISO(parseDateTime("2023-01-22")).split(".")[0]).toBe(
        "2023-01-22T00:00:00",
    );
});

test("strftimeToDateFormat: the no-padding flag is a flag, not a literal", () => {
    expect(strftimeToDateFormat("%-d/%m/%Y")).toBe("d/MM/yyyy");
    expect(strftimeToDateFormat("%-I:%M")).toBe("h:mm");
});

test("toLocaleDateTimeString omits the year of the date it shows, not of the value's zone", () => {
    mockTimeZone(+2);
    mockDate("2027-01-01 12:00:00");
    const lastYearInUtc = parseISO("2026-12-31T23:30:00", "UTC");
    expect(toLocaleDateTimeString(lastYearInUtc)).not.toInclude("2026");
    expect(toLocaleDateTimeString(lastYearInUtc, { tz: "utc" })).toInclude("2026");
});
