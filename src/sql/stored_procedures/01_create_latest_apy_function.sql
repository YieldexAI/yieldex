create or replace function get_latest_apy()
returns table (
    pool_id text,
    asset text,
    chain text,
    apy numeric,
    tvl numeric,
    is_tweeted boolean,
    apy_base numeric,
    apy_reward numeric,
    apy_mean_30d numeric,
    apy_change_1d numeric,
    apy_change_7d numeric,
    apy_change_30d numeric,
    apy_timestamp bigint
) as $$
    select distinct on (pool_id) 
        pool_id, asset, chain, apy, tvl, is_tweeted, 
        apy_base, apy_reward, apy_mean_30d,
        apy_change_1d, apy_change_7d, apy_change_30d,
        timestamp as apy_timestamp
    from apy_history
    order by pool_id, timestamp desc
$$ language sql stable;