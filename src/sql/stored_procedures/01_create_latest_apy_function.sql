CREATE OR REPLACE FUNCTION get_latest_apy()
RETURNS TABLE (
    id uuid,
    asset text,
    chain text,
    apy float8,
    recorded_at bigint,
    pool_id text,
    created_at timestamp with time zone
) AS $$
    WITH latest_records AS (
        SELECT pool_id, MAX("timestamp") as max_time
        FROM apy_history
        GROUP BY pool_id
    )
    SELECT ah.*
    FROM apy_history ah
    JOIN latest_records lr 
        ON ah.pool_id = lr.pool_id 
        AND ah."timestamp" = lr.max_time
    ORDER BY ah."timestamp" DESC;
$$ LANGUAGE SQL; 