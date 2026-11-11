-- AETHENTRA ML-04 metadata schema for PostgreSQL / Supabase.
-- NOT APPLIED: no Supabase project is configured for this repository. The local pipeline uses the same tables in SQLite
-- (data/processed/ml04/ml04.sqlite). Large rasters stay in object storage (NetCDF / GeoTIFF); rows reference logical product ids.
create table if not exists ml04_models (
  id text primary key, name text not null, family text not null, params jsonb, trained_utc timestamptz,
  baseline_period text, train_period text, thresholds jsonb, selected boolean default false);
create table if not exists ml04_datasets (
  id text primary key, name text, version text, doi text, coverage_start date, coverage_end date, resolution text,
  access text, licence text, recorded_utc timestamptz);
create table if not exists ml04_anomaly_events (
  id bigserial primary key, model_id text references ml04_models(id), variable text not null, anomaly_type text,
  severity text check (severity in ('mild','moderate','strong','extreme')), anomaly_score double precision,
  confidence text, latitude double precision, longitude double precision, region text, observation_timestamp date,
  baseline_period text, source_dataset text, output_file_path text, created_at timestamptz default now(),
  observed_value double precision, baseline_mean double precision, percentile double precision, method text,
  top_variables text, method_agreement smallint, data_tier text);
create index if not exists ml04_ev_time on ml04_anomaly_events (observation_timestamp);
create index if not exists ml04_ev_var on ml04_anomaly_events (variable, severity);
create table if not exists ml04_processing_runs (
  id bigserial primary key, started_utc timestamptz, finished_utc timestamptz, status text, stages jsonb, details jsonb);
-- Row-level security should be enabled before exposing these tables through the Supabase API:
alter table ml04_models enable row level security;
alter table ml04_datasets enable row level security;
alter table ml04_anomaly_events enable row level security;
alter table ml04_processing_runs enable row level security;
