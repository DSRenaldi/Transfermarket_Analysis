"""Run the Phase 1 source-data audit against PostgreSQL staging tables."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

import psycopg
from psycopg import sql

from db_connection import connect


RAW_SCHEMA = "tm_raw"
AUDIT_SCHEMA = "tm_audit"
REF_SCHEMA = "tm_ref"
REPORT_DIR = Path("reports/data_audit")
DATE_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$"
NUMERIC_PATTERN = r"^-?[0-9]+(?:\.[0-9]+)?$"
BIG_FIVE_COMPETITIONS = {"GB1", "ES1", "IT1", "L1", "FR1"}

KEY_RULES = (
    ("competitions", "competition_id", ("competition_id",), True),
    ("clubs", "club_id", ("club_id",), True),
    ("players", "player_id", ("player_id",), True),
    ("games", "game_id", ("game_id",), True),
    ("appearances", "appearance_id", ("appearance_id",), True),
    ("appearances", "player_game", ("player_id", "game_id"), True),
    ("player_valuations", "player_date", ("player_id", "date"), True),
    ("club_games", "club_game", ("club_id", "game_id"), True),
    ("game_events", "game_event_id", ("game_event_id",), True),
    ("game_lineups", "game_lineups_id", ("game_lineups_id",), True),
    ("countries", "country_id", ("country_id",), True),
    ("national_teams", "national_team_id", ("national_team_id",), True),
)

FOREIGN_KEY_RULES = (
    ("clubs", "domestic_competition_id", "competitions", "competition_id"),
    ("players", "current_club_id", "clubs", "club_id"),
    ("games", "competition_id", "competitions", "competition_id"),
    ("games", "home_club_id", "clubs", "club_id"),
    ("games", "away_club_id", "clubs", "club_id"),
    ("appearances", "game_id", "games", "game_id"),
    ("appearances", "player_id", "players", "player_id"),
    ("appearances", "player_club_id", "clubs", "club_id"),
    ("player_valuations", "player_id", "players", "player_id"),
    ("player_valuations", "current_club_id", "clubs", "club_id"),
    ("club_games", "game_id", "games", "game_id"),
    ("club_games", "club_id", "clubs", "club_id"),
    ("club_games", "opponent_id", "clubs", "club_id"),
    ("game_events", "game_id", "games", "game_id"),
    ("game_events", "player_id", "players", "player_id"),
    ("game_events", "club_id", "clubs", "club_id"),
    ("game_lineups", "game_id", "games", "game_id"),
    ("game_lineups", "player_id", "players", "player_id"),
    ("game_lineups", "club_id", "clubs", "club_id"),
    ("transfers", "player_id", "players", "player_id"),
    ("transfers", "from_club_id", "clubs", "club_id"),
    ("transfers", "to_club_id", "clubs", "club_id"),
    ("national_teams", "country_id", "countries", "country_id"),
)

DATE_FIELDS = (
    ("games", "date"),
    ("appearances", "date"),
    ("player_valuations", "date"),
    ("game_events", "date"),
    ("game_lineups", "date"),
    ("transfers", "transfer_date"),
)

NUMERIC_RULES = (
    ("players", "height_in_cm", 100, 230),
    ("players", "market_value_in_eur", 0, None),
    ("players", "highest_market_value_in_eur", 0, None),
    ("appearances", "minutes_played", 0, 130),
    ("appearances", "goals", 0, None),
    ("appearances", "assists", 0, None),
    ("appearances", "yellow_cards", 0, None),
    ("appearances", "red_cards", 0, None),
    ("player_valuations", "market_value_in_eur", 0, None),
    ("games", "home_club_goals", 0, None),
    ("games", "away_club_goals", 0, None),
    ("games", "attendance", 0, None),
    ("transfers", "transfer_fee", 0, None),
    ("transfers", "market_value_in_eur", 0, None),
)


def serialize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(name: str, rows: list[dict[str, Any]]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{name}.csv"
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {key: serialize(value) for key, value in row.items()} for row in rows
        )


def publish_table(
    conn: psycopg.Connection, name: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    columns = list(rows[0])
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                sql.Identifier(AUDIT_SCHEMA)
            )
        )
        cur.execute(
            sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
                sql.Identifier(AUDIT_SCHEMA), sql.Identifier(name)
            )
        )
        cur.execute(
            sql.SQL("CREATE TABLE {}.{} ({})").format(
                sql.Identifier(AUDIT_SCHEMA),
                sql.Identifier(name),
                sql.SQL(", ").join(
                    sql.SQL("{} TEXT").format(sql.Identifier(column))
                    for column in columns
                ),
            )
        )
        statement = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(AUDIT_SCHEMA),
            sql.Identifier(name),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        cur.executemany(
            statement,
            [tuple(serialize(row[column]) for column in columns) for row in rows],
        )
    conn.commit()


def raw_columns(cur: psycopg.Cursor, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
          AND column_name NOT LIKE '\\_%%' ESCAPE '\\'
        ORDER BY ordinal_position
        """,
        (RAW_SCHEMA, table),
    )
    return [row[0] for row in cur.fetchall()]


def table_profiles(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (RAW_SCHEMA,),
    )
    tables = [row[0] for row in cur.fetchall()]
    rows: list[dict[str, Any]] = []
    for table in tables:
        columns = raw_columns(cur, table)
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                sql.Identifier(RAW_SCHEMA), sql.Identifier(table)
            )
        )
        rows.append(
            {
                "table_name": table,
                "row_count": cur.fetchone()[0],
                "source_column_count": len(columns),
            }
        )
    return rows


def missingness_profiles(
    cur: psycopg.Cursor, profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for profile in profiles:
        table = profile["table_name"]
        columns = raw_columns(cur, table)
        expressions = [sql.SQL("COUNT(*)")]
        for column in columns:
            expressions.append(
                sql.SQL("COUNT(*) FILTER (WHERE NULLIF(BTRIM({}), '') IS NULL)").format(
                    sql.Identifier(column)
                )
            )
        cur.execute(
            sql.SQL("SELECT {} FROM {}.{}").format(
                sql.SQL(", ").join(expressions),
                sql.Identifier(RAW_SCHEMA),
                sql.Identifier(table),
            )
        )
        result = cur.fetchone()
        total = result[0]
        for index, column in enumerate(columns, start=1):
            missing = result[index]
            output.append(
                {
                    "table_name": table,
                    "column_name": column,
                    "row_count": total,
                    "missing_count": missing,
                    "missing_pct": round(missing / total * 100, 4) if total else None,
                }
            )
    return output


def key_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for table, check_name, columns, expected_unique in KEY_RULES:
        null_condition = sql.SQL(" OR ").join(
            sql.SQL("NULLIF(BTRIM({}), '') IS NULL").format(sql.Identifier(column))
            for column in columns
        )
        cur.execute(
            sql.SQL("SELECT COUNT(*), COUNT(*) FILTER (WHERE {}) FROM {}.{}").format(
                null_condition,
                sql.Identifier(RAW_SCHEMA),
                sql.Identifier(table),
            )
        )
        row_count, null_key_rows = cur.fetchone()
        group_columns = sql.SQL(", ").join(map(sql.Identifier, columns))
        cur.execute(
            sql.SQL(
                "SELECT COUNT(*), COALESCE(SUM(group_size - 1), 0) "
                "FROM (SELECT COUNT(*) AS group_size FROM {}.{} "
                "WHERE NOT ({}) GROUP BY {} HAVING COUNT(*) > 1) duplicate_groups"
            ).format(
                sql.Identifier(RAW_SCHEMA),
                sql.Identifier(table),
                null_condition,
                group_columns,
            )
        )
        duplicate_groups, duplicate_rows = cur.fetchone()
        passed = null_key_rows == 0 and (not expected_unique or duplicate_rows == 0)
        output.append(
            {
                "table_name": table,
                "check_name": check_name,
                "key_columns": ",".join(columns),
                "expected_unique": expected_unique,
                "row_count": row_count,
                "null_key_rows": null_key_rows,
                "duplicate_groups": duplicate_groups,
                "duplicate_excess_rows": duplicate_rows,
                "status": "PASS" if passed else "FAIL",
            }
        )

    transfer_columns = raw_columns(cur, "transfers")
    grouped = sql.SQL(", ").join(map(sql.Identifier, transfer_columns))
    cur.execute(
        sql.SQL(
            "SELECT COUNT(*), COALESCE(SUM(group_size - 1), 0) "
            "FROM (SELECT COUNT(*) AS group_size FROM {}.{} GROUP BY {} "
            "HAVING COUNT(*) > 1) duplicate_groups"
        ).format(
            sql.Identifier(RAW_SCHEMA), sql.Identifier("transfers"), grouped
        )
    )
    duplicate_groups, duplicate_rows = cur.fetchone()
    cur.execute(
        sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(RAW_SCHEMA), sql.Identifier("transfers")
        )
    )
    transfer_row_count = cur.fetchone()[0]
    output.append(
        {
            "table_name": "transfers",
            "check_name": "exact_source_row",
            "key_columns": "all source columns",
            "expected_unique": True,
            "row_count": transfer_row_count,
            "null_key_rows": "not_applicable",
            "duplicate_groups": duplicate_groups,
            "duplicate_excess_rows": duplicate_rows,
            "status": "PASS" if duplicate_rows == 0 else "FAIL",
        }
    )
    return output


def foreign_key_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for child, child_column, parent, parent_column in FOREIGN_KEY_RULES:
        query = sql.SQL(
            "WITH parent_keys AS (SELECT DISTINCT {parent_col} AS key FROM {schema}.{parent} "
            "WHERE NULLIF(BTRIM({parent_col}), '') IS NOT NULL) "
            "SELECT COUNT(*) FILTER (WHERE NULLIF(BTRIM(c.{child_col}), '') IS NOT NULL), "
            "COUNT(*) FILTER (WHERE NULLIF(BTRIM(c.{child_col}), '') IS NOT NULL AND p.key IS NULL), "
            "COUNT(DISTINCT c.{child_col}) FILTER (WHERE NULLIF(BTRIM(c.{child_col}), '') IS NOT NULL AND p.key IS NULL) "
            "FROM {schema}.{child} c LEFT JOIN parent_keys p ON c.{child_col} = p.key"
        ).format(
            schema=sql.Identifier(RAW_SCHEMA),
            child=sql.Identifier(child),
            child_col=sql.Identifier(child_column),
            parent=sql.Identifier(parent),
            parent_col=sql.Identifier(parent_column),
        )
        cur.execute(query)
        nonnull_rows, orphan_rows, orphan_values = cur.fetchone()
        output.append(
            {
                "child_table": child,
                "child_column": child_column,
                "parent_table": parent,
                "parent_column": parent_column,
                "nonnull_child_rows": nonnull_rows,
                "orphan_rows": orphan_rows,
                "orphan_distinct_values": orphan_values,
                "orphan_pct": round(orphan_rows / nonnull_rows * 100, 4)
                if nonnull_rows
                else 0,
                "status": "PASS" if orphan_rows == 0 else "REVIEW",
            }
        )
    return output


def date_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for table, column in DATE_FIELDS:
        field = sql.Identifier(column)
        cur.execute(
            sql.SQL(
                "SELECT COUNT(*), "
                "COUNT(*) FILTER (WHERE NULLIF(BTRIM({field}), '') IS NULL), "
                "COUNT(*) FILTER (WHERE NULLIF(BTRIM({field}), '') IS NOT NULL AND NOT ({field} ~ %s)), "
                "MIN(CASE WHEN {field} ~ %s THEN {field}::date END), "
                "MAX(CASE WHEN {field} ~ %s THEN {field}::date END), "
                "COUNT(*) FILTER (WHERE {field} ~ %s AND {field}::date > CURRENT_DATE) "
                "FROM {schema}.{table}"
            ).format(
                field=field,
                schema=sql.Identifier(RAW_SCHEMA),
                table=sql.Identifier(table),
            ),
            (DATE_PATTERN, DATE_PATTERN, DATE_PATTERN, DATE_PATTERN),
        )
        row_count, missing, invalid, minimum, maximum, future = cur.fetchone()
        output.append(
            {
                "table_name": table,
                "column_name": column,
                "row_count": row_count,
                "missing_count": missing,
                "invalid_format_count": invalid,
                "min_date": minimum,
                "max_date": maximum,
                "future_date_count": future,
                "status": "PASS" if invalid == 0 and future == 0 else "REVIEW",
            }
        )
    return output


def numeric_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for table, column, minimum, maximum in NUMERIC_RULES:
        field = sql.Identifier(column)
        upper_bound_expression = (
            sql.SQL(
                "COUNT(*) FILTER (WHERE {field} ~ %s AND {field}::numeric > %s)"
            ).format(field=field)
            if maximum is not None
            else sql.SQL("0::bigint")
        )
        parameters: list[Any] = [
            NUMERIC_PATTERN,
            NUMERIC_PATTERN,
            minimum,
        ]
        if maximum is not None:
            parameters.extend((NUMERIC_PATTERN, maximum))
        cur.execute(
            sql.SQL(
                "SELECT COUNT(*), "
                "COUNT(*) FILTER (WHERE NULLIF(BTRIM({field}), '') IS NULL), "
                "COUNT(*) FILTER (WHERE NULLIF(BTRIM({field}), '') IS NOT NULL AND NOT ({field} ~ %s)), "
                "COUNT(*) FILTER (WHERE {field} ~ %s AND {field}::numeric < %s), "
                "{upper_bound_expression} "
                "FROM {schema}.{table}"
            ).format(
                field=field,
                upper_bound_expression=upper_bound_expression,
                schema=sql.Identifier(RAW_SCHEMA),
                table=sql.Identifier(table),
            ),
            parameters,
        )
        row_count, missing, invalid, below_min, above_max = cur.fetchone()
        output.append(
            {
                "table_name": table,
                "column_name": column,
                "row_count": row_count,
                "missing_count": missing,
                "invalid_format_count": invalid,
                "minimum_allowed": minimum,
                "below_minimum_count": below_min,
                "maximum_allowed": maximum,
                "above_maximum_count": above_max,
                "status": "PASS"
                if invalid == 0 and below_min == 0 and above_max == 0
                else "REVIEW",
            }
        )
    return output


def mapping_checks(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    queries = {
        "player_position": sql.SQL(
            "SELECT COALESCE(m.position_group, 'UNMAPPED'), COUNT(*) "
            "FROM {raw}.players p LEFT JOIN {ref}.position_mapping m "
            "ON p.position = m.source_position "
            "AND COALESCE(p.sub_position, '') = COALESCE(m.source_sub_position, '') "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).format(raw=sql.Identifier(RAW_SCHEMA), ref=sql.Identifier(REF_SCHEMA)),
        "competition_type": sql.SQL(
            "SELECT COALESCE(m.competition_group, 'UNMAPPED'), COUNT(*) "
            "FROM {raw}.competitions c LEFT JOIN {ref}.competition_type_mapping m "
            "ON COALESCE(c.type, '') = COALESCE(m.source_type, '') "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).format(raw=sql.Identifier(RAW_SCHEMA), ref=sql.Identifier(REF_SCHEMA)),
        "game_competition_type": sql.SQL(
            "SELECT COALESCE(o.competition_group, m.competition_group, 'UNMAPPED'), COUNT(*) "
            "FROM {raw}.games g "
            "LEFT JOIN {ref}.competition_id_overrides o ON g.competition_id = o.competition_id "
            "LEFT JOIN {ref}.competition_type_mapping m "
            "ON COALESCE(g.competition_type, '') = COALESCE(m.source_type, '') "
            "GROUP BY 1 ORDER BY 2 DESC"
        ).format(raw=sql.Identifier(RAW_SCHEMA), ref=sql.Identifier(REF_SCHEMA)),
        "transfer_fee_status": sql.SQL(
            "SELECT CASE "
            "WHEN transfer_fee IS NULL THEN 'unknown_or_undisclosed' "
            "WHEN transfer_fee !~ %s THEN 'invalid_format' "
            "WHEN transfer_fee::numeric < 0 THEN 'invalid_negative' "
            "WHEN transfer_fee::numeric = 0 THEN 'recorded_zero_ambiguous' "
            "ELSE 'numeric_fee' END AS category, COUNT(*) "
            "FROM {raw}.transfers GROUP BY 1 ORDER BY 2 DESC"
        ).format(raw=sql.Identifier(RAW_SCHEMA)),
    }
    output: list[dict[str, Any]] = []
    for check_name, query in queries.items():
        cur.execute(query, (NUMERIC_PATTERN,) if check_name == "transfer_fee_status" else ())
        result = cur.fetchall()
        total = sum(row[1] for row in result)
        for category, count in result:
            output.append(
                {
                    "check_name": check_name,
                    "category": category,
                    "row_count": count,
                    "row_pct": round(count / total * 100, 4) if total else None,
                    "status": "REVIEW" if category in {"UNMAPPED", "invalid_format", "invalid_negative"} else "OK",
                }
            )
    return output


def competition_season_coverage(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        sql.SQL(
            "WITH game_summary AS ("
            " SELECT competition_id, season, COUNT(*) AS game_count,"
            " MIN(CASE WHEN date ~ %s THEN date::date END) AS min_game_date,"
            " MAX(CASE WHEN date ~ %s THEN date::date END) AS max_game_date"
            " FROM {raw}.games GROUP BY competition_id, season"
            "), appearance_summary AS ("
            " SELECT g.competition_id, g.season, COUNT(*) AS appearance_rows,"
            " COUNT(DISTINCT a.player_id) AS players_with_appearances,"
            " SUM(CASE WHEN a.minutes_played ~ %s THEN a.minutes_played::numeric ELSE 0 END) AS total_minutes"
            " FROM {raw}.appearances a JOIN {raw}.games g ON a.game_id = g.game_id"
            " GROUP BY g.competition_id, g.season"
            ")"
            " SELECT gs.competition_id, COALESCE(c.name, o.competition_name) AS competition_name,"
            " COALESCE(c.country_name, o.country_name) AS country_name,"
            " COALESCE(c.type, o.source_type) AS competition_type,"
            " gs.season, gs.game_count, gs.min_game_date, gs.max_game_date,"
            " COALESCE(ap.appearance_rows, 0), COALESCE(ap.players_with_appearances, 0), COALESCE(ap.total_minutes, 0)"
            " FROM game_summary gs"
            " LEFT JOIN {raw}.competitions c ON gs.competition_id = c.competition_id"
            " LEFT JOIN {ref}.competition_id_overrides o ON gs.competition_id = o.competition_id"
            " LEFT JOIN appearance_summary ap ON gs.competition_id = ap.competition_id AND gs.season = ap.season"
            " ORDER BY gs.competition_id, gs.season"
        ).format(raw=sql.Identifier(RAW_SCHEMA), ref=sql.Identifier(REF_SCHEMA)),
        (DATE_PATTERN, DATE_PATTERN, NUMERIC_PATTERN),
    )
    columns = (
        "competition_id",
        "competition_name",
        "country_name",
        "competition_type",
        "season",
        "game_count",
        "min_game_date",
        "max_game_date",
        "appearance_rows",
        "players_with_appearances",
        "total_minutes",
    )
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    by_competition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_competition[row["competition_id"]].append(row)

    for competition_rows in by_competition.values():
        ordered = sorted(
            competition_rows,
            key=lambda row: int(row["season"]) if str(row["season"]).isdigit() else -1,
        )
        for index, row in enumerate(ordered):
            local_window = ordered[max(0, index - 2) : index + 3]
            local_baseline = median(item["game_count"] for item in local_window)
            ratio = row["game_count"] / local_baseline if local_baseline else None
            row["game_count_vs_local_median_pct"] = round(ratio * 100, 2) if ratio is not None else None
            row["coverage_status"] = (
                "ADEQUATE"
                if ratio is not None and ratio >= 0.85 and row["appearance_rows"] > 0
                else "REVIEW"
            )
    return rows


def recommended_scope(coverage: list[dict[str, Any]]) -> dict[str, Any]:
    adequate_by_competition: dict[str, set[int]] = {}
    for competition_id in BIG_FIVE_COMPETITIONS:
        adequate_by_competition[competition_id] = {
            int(row["season"])
            for row in coverage
            if row["competition_id"] == competition_id
            and str(row["season"]).isdigit()
            and row["coverage_status"] == "ADEQUATE"
        }
    common = set.intersection(*adequate_by_competition.values()) if adequate_by_competition else set()
    seasons = sorted(common, reverse=True)[:3]
    return {
        "competition_ids": sorted(BIG_FIVE_COMPETITIONS),
        "latest_three_common_adequate_seasons": seasons,
        "minimum_minutes": 900,
        "player_scope": "outfield",
        "season_end_value_definition": "latest valuation on or before the documented season end date",
        "adequacy_rule": "game count >= 85% of the competition's five-season local median and appearance coverage > 0",
    }


def markdown_report(
    summary: dict[str, Any],
    keys: list[dict[str, Any]],
    foreign_keys: list[dict[str, Any]],
    missingness: list[dict[str, Any]],
    numerics: list[dict[str, Any]],
    mappings: list[dict[str, Any]],
) -> str:
    failed_keys = [row for row in keys if row["status"] == "FAIL"]
    orphan_checks = [row for row in foreign_keys if row["orphan_rows"] > 0]
    high_missing = sorted(
        (row for row in missingness if row["missing_pct"] is not None and row["missing_pct"] >= 20),
        key=lambda row: row["missing_pct"],
        reverse=True,
    )[:15]
    numeric_reviews = [row for row in numerics if row["status"] != "PASS"]
    mapping_reviews = [row for row in mappings if row["status"] == "REVIEW"]
    fee_coverage = [
        row for row in mappings if row["check_name"] == "transfer_fee_status"
    ]
    dates = summary["date_coverage"]
    scope = summary["recommended_v1_scope"]

    lines = [
        "# Phase 1 Data Audit",
        "",
        f"Generated at: `{summary['generated_at_utc']}`",
        "",
        "## Snapshot",
        "",
    ]
    for row in dates:
        lines.append(
            f"- `{row['table_name']}.{row['column_name']}`: {serialize(row['min_date'])} to {serialize(row['max_date'])}; "
            f"missing={row['missing_count']}, invalid={row['invalid_format_count']}, future={row['future_date_count']}."
        )
    lines.extend(
        [
            "",
            "## Recommended v1 scope",
            "",
            f"- Competitions: {', '.join(scope['competition_ids'])}.",
            f"- Seasons: {', '.join(map(str, scope['latest_three_common_adequate_seasons'])) or 'No common three-season window passed automatically'}.",
            f"- Players: {scope['player_scope']}, minimum {scope['minimum_minutes']} minutes.",
            f"- Coverage rule: {scope['adequacy_rule']}.",
            "",
            "## Key integrity",
            "",
            f"- Checks run: {len(keys)}; failed: {len(failed_keys)}.",
        ]
    )
    for row in failed_keys:
        lines.append(
            f"- FAIL `{row['table_name']}` / `{row['check_name']}`: null rows={row['null_key_rows']}, "
            f"duplicate excess rows={row['duplicate_excess_rows']}."
        )
    lines.extend(["", "## Numeric quality", ""])
    if not numeric_reviews:
        lines.append("- All configured numeric format and range checks passed.")
    for row in numeric_reviews:
        lines.append(
            f"- REVIEW `{row['table_name']}.{row['column_name']}`: "
            f"invalid={row['invalid_format_count']}, below minimum={row['below_minimum_count']}, "
            f"above maximum={row['above_maximum_count']}."
        )
    lines.extend(["", "## Mapping and fee coverage", ""])
    lines.append(
        f"- Unmapped or invalid mapping categories: {len(mapping_reviews)}."
    )
    for row in fee_coverage:
        lines.append(
            f"- Transfer fee `{row['category']}`: {row['row_count']} rows ({row['row_pct']}%)."
        )
    lines.extend(
        [
            "",
            "## Referential integrity",
            "",
            f"- Checks with orphan values: {len(orphan_checks)} of {len(foreign_keys)}.",
        ]
    )
    for row in sorted(orphan_checks, key=lambda item: item["orphan_rows"], reverse=True)[:15]:
        lines.append(
            f"- REVIEW `{row['child_table']}.{row['child_column']}` -> "
            f"`{row['parent_table']}.{row['parent_column']}`: {row['orphan_rows']} rows "
            f"({row['orphan_pct']}%)."
        )
    lines.extend(["", "## High missingness", ""])
    for row in high_missing:
        lines.append(
            f"- `{row['table_name']}.{row['column_name']}`: {row['missing_pct']}% missing."
        )
    lines.extend(
        [
            "",
            "## Method notes",
            "",
            "- Raw CSV values are loaded as text so source semantics are preserved before typing and cleaning.",
            "- A recorded transfer fee of zero remains ambiguous; it is not automatically labeled as a free transfer.",
            "- Foreign-key exceptions can reflect national teams, defunct clubs, or incomplete entity coverage and require contextual review.",
            "- The automatic coverage rule is a screening heuristic, not a guarantee that every round or appearance is complete.",
            "- Detailed evidence is available in the CSV files in this directory and in the `tm_audit` PostgreSQL schema.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    with connect() as conn:
        with conn.cursor() as cur:
            profiles = table_profiles(cur)
            missingness = missingness_profiles(cur, profiles)
            keys = key_checks(cur)
            foreign_keys = foreign_key_checks(cur)
            dates = date_checks(cur)
            numerics = numeric_checks(cur)
            mappings = mapping_checks(cur)
            coverage = competition_season_coverage(cur)

        reports = {
            "table_profile": profiles,
            "column_missingness": missingness,
            "key_checks": keys,
            "foreign_key_checks": foreign_keys,
            "date_coverage": dates,
            "numeric_quality": numerics,
            "mapping_coverage": mappings,
            "competition_season_coverage": coverage,
        }
        for name, rows in reports.items():
            print(f"Publishing {name} ...", flush=True)
            write_csv(name, rows)
            publish_table(conn, name, rows)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "table_count": len(profiles),
        "total_source_rows": sum(row["row_count"] for row in profiles),
        "failed_key_checks": sum(row["status"] == "FAIL" for row in keys),
        "foreign_key_checks_with_orphans": sum(
            row["orphan_rows"] > 0 for row in foreign_keys
        ),
        "date_coverage": dates,
        "recommended_v1_scope": recommended_scope(coverage),
    }
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "phase1_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=serialize) + "\n",
        encoding="utf-8",
    )
    (REPORT_DIR / "phase1-audit.md").write_text(
        markdown_report(summary, keys, foreign_keys, missingness, numerics, mappings),
        encoding="utf-8",
    )
    print(f"Phase 1 audit written to {REPORT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
