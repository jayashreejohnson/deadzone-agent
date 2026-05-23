CREATE TABLE IF NOT EXISTS users (
  user_id String,
  interests Array(String),
  wallet_address String
) ENGINE = MergeTree() ORDER BY user_id;

CREATE TABLE IF NOT EXISTS packs (
  pack_id String,
  route_id String,
  deadzone_id String,
  url String,
  owner_user_id String,
  created_at DateTime DEFAULT now(),
  source_count UInt32
) ENGINE = MergeTree() ORDER BY (route_id, deadzone_id, created_at);

CREATE TABLE IF NOT EXISTS events (
  event_id String,
  user_id String,
  route_id String,
  deadzone_id String,
  action String,
  pack_id String,
  build_ms UInt32,
  ts DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY ts;

CREATE TABLE IF NOT EXISTS payments (
  tx_id String,
  from_user String,
  to_user String,
  amount_usd Float32,
  pack_id String,
  ts DateTime DEFAULT now()
) ENGINE = MergeTree() ORDER BY ts;
