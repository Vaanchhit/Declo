create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.workspaces (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  trackers jsonb not null default '[]'::jsonb,
  data jsonb not null default '{}'::jsonb,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.parse_requests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  input_text text not null,
  result_json jsonb,
  status text not null default 'succeeded',
  model text,
  latency_ms integer,
  error_message text,
  created_at timestamptz not null default timezone('utc', now())
);

create trigger set_profiles_updated_at
before update on public.profiles
for each row
execute function public.set_updated_at();

create trigger set_workspaces_updated_at
before update on public.workspaces
for each row
execute function public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.workspaces enable row level security;
alter table public.parse_requests enable row level security;

create policy "profiles_select_own"
on public.profiles
for select
using (auth.uid() = id);

create policy "profiles_insert_own"
on public.profiles
for insert
with check (auth.uid() = id);

create policy "profiles_update_own"
on public.profiles
for update
using (auth.uid() = id)
with check (auth.uid() = id);

create policy "workspaces_select_own"
on public.workspaces
for select
using (auth.uid() = user_id);

create policy "workspaces_insert_own"
on public.workspaces
for insert
with check (auth.uid() = user_id);

create policy "workspaces_update_own"
on public.workspaces
for update
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

create policy "workspaces_delete_own"
on public.workspaces
for delete
using (auth.uid() = user_id);

create policy "parse_requests_select_own"
on public.parse_requests
for select
using (auth.uid() = user_id);

create policy "parse_requests_insert_own"
on public.parse_requests
for insert
with check (auth.uid() = user_id);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'name', split_part(coalesce(new.email, ''), '@', 1))
  )
  on conflict (id) do nothing;

  insert into public.workspaces (user_id)
  values (new.id)
  on conflict (user_id) do nothing;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row
execute procedure public.handle_new_user();

