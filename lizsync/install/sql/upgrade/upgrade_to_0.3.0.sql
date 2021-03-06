BEGIN;

DROP FUNCTION IF EXISTS lizsync.get_event_sql(bigint, text);
DROP FUNCTION IF EXISTS lizsync.get_event_sql(bigint, text, text[]);

CREATE FUNCTION lizsync.get_event_sql(pevent_id bigint, puid_column text, excluded_columns text[]) RETURNS text
    LANGUAGE plpgsql
    AS $$
DECLARE
  sql text;
BEGIN
    IF excluded_columns IS NULL THEN
        excluded_columns:= '{}'::text[];
    END IF;

    WITH
    event AS (
        SELECT * FROM audit.logged_actions WHERE event_id = pevent_id
    )
    -- get primary key names
    , where_pks AS (
        SELECT array_agg(uid_column) as pkey_fields
        FROM audit.logged_relations r
        JOIN event ON relation_name = (quote_ident(schema_name) || '.' || quote_ident(table_name))
    )
    -- create where clause with uid column
    -- not with primary keys, to manage multi-way sync
    , where_uid AS (
        SELECT '"' || puid_column || '" = ' || quote_literal(row_data->puid_column) AS where_clause
        FROM event
    )
    SELECT INTO sql
        CASE
            WHEN action = 'I' THEN
                'INSERT INTO "' || schema_name || '"."' || table_name || '"' ||
                ' (' || (
                    SELECT string_agg(
                        '"' || key || '"',
                        ','
                    )
                    FROM each(row_data)
                    WHERE True
                    AND key != ALL(pkey_fields)
                    AND key != ALL(excluded_columns)
                )
                || ') VALUES ( ' ||
                (
                    SELECT string_agg(
                        CASE WHEN value IS NULL THEN 'NULL' ELSE quote_literal(value) END,
                        ','
                    )
                    FROM EACH(row_data)
                    WHERE True
                    AND key != ALL(pkey_fields)
                    AND key != ALL(excluded_columns)
                )
                || ')'

            WHEN action = 'D' THEN
                'DELETE FROM "' || schema_name || '"."' || table_name || '"' ||
                ' WHERE ' || where_clause

            WHEN action = 'U' THEN
                'UPDATE "' || schema_name || '"."' || table_name || '"' ||
                ' SET ' || (
                    SELECT string_agg(
                        '"' || key || '"' || ' = ' ||
                        CASE
                            WHEN value IS NULL
                                THEN 'NULL'
                            ELSE quote_literal(value)
                        END,
                        ','
                    ) FROM each(changed_fields)
                    WHERE True
                    AND key != ALL(pkey_fields)
                    AND key != ALL(excluded_columns)
                ) ||
                ' WHERE ' || where_clause
        END
    FROM
        event, where_pks, where_uid
    ;
    RETURN sql;
END;
$$;

COMMENT ON FUNCTION lizsync.get_event_sql(pevent_id bigint, puid_column text, excluded_columns text[]) IS '
Get the SQL to use for replay from a audit log event

Arguments:
   pevent_id:  The event_id of the event in audit.logged_actions to replay
   puid_column: The name of the column with unique uuid values
';


COMMIT;
