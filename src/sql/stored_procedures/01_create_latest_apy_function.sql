create or replace function get_latest_apy()
returns table (
    pool_id text,
    asset text,
    chain text,
    apy numeric,
    tvl numeric,
    is_tweeted boolean,
    apy_timestamp bigint
) as $$
    select distinct on (pool_id) 
        pool_id, asset, chain, apy, tvl, is_tweeted, timestamp as apy_timestamp
    from apy_history
    order by pool_id, timestamp desc
$$ language sql stable;