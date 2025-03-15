create table if not exists pool_balances (
    id uuid default uuid_generate_v4() primary key,
    pool_id text not null references apy_history(pool_id),
    position_balance numeric not null,  -- Pool balance (in USD)
    timestamp bigint not null,       -- Data update timestamp
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
    
    constraint pool_balances_unique_pool_timestamp unique (pool_id, timestamp)
);

-- Index for fast lookup of latest updates
create index if not exists pool_balances_timestamp_idx on pool_balances(timestamp desc);

-- Trigger for automatic updated_at update
create or replace function update_updated_at_column()
returns trigger as $$
begin
    NEW.updated_at = now();
    return NEW;
end;
$$ language 'plpgsql';

create trigger update_pool_balances_updated_at
    before update on pool_balances
    for each row
    execute procedure update_updated_at_column();