-- Shared Supabase schema for doomberg.me and kural.website.
-- Apply in Supabase SQL editor or with: supabase db push

create extension if not exists pgcrypto;

create table if not exists public.tenants (
  id text primary key,
  display_name text not null,
  primary_host text not null unique,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.tenants (id, display_name, primary_host)
values
  ('doomberg', 'Doomberg', 'doomberg.me'),
  ('kural', 'Kural', 'kural.website')
on conflict (id) do update set
  display_name = excluded.display_name,
  primary_host = excluded.primary_host,
  updated_at = now();

create table if not exists public.ai_interactions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null references public.tenants(id) on delete cascade,
  host text not null,
  session_id text not null,
  request_kind text not null,
  prompt text,
  response text,
  status text not null check (status in ('ok', 'error')),
  error text,
  latency_ms integer,
  created_at timestamptz not null default now()
);

create index if not exists ai_interactions_tenant_created_idx
  on public.ai_interactions (tenant_id, created_at desc);
create index if not exists ai_interactions_session_idx
  on public.ai_interactions (session_id, created_at desc);

create table if not exists public.saved_dashboards (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null references public.tenants(id) on delete cascade,
  user_id text not null default 'operator',
  name text not null,
  summary text not null default '',
  panels jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists saved_dashboards_tenant_updated_idx
  on public.saved_dashboards (tenant_id, updated_at desc);

alter table public.tenants enable row level security;
alter table public.ai_interactions enable row level security;
alter table public.saved_dashboards enable row level security;

-- No anonymous public policies are created on purpose.
-- Vercel serverless functions use SUPABASE_SERVICE_ROLE_KEY server-side only.
