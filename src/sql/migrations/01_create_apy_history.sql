create table if not exists apy_history (
    id uuid default uuid_generate_v4() primary key,
    asset text not null,
    chain text not null,
    apy float8 not null,
    timestamp bigint not null,
    pool_id text not null,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    
    constraint apy_history_unique_pool_timestamp unique (pool_id, timestamp)
);

-- Create index for faster queries
create index if not exists apy_history_timestamp_idx on apy_history(timestamp desc); 