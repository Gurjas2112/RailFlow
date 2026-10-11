-- backend/railflow/schema.sql — RailFlow SQLite schema (SPEC §31). Idempotent.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id          INTEGER PRIMARY KEY,
  username    TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 32),
  pw_hash     TEXT NOT NULL,                       -- Argon2id encoded string
  role        TEXT NOT NULL CHECK (role IN ('viewer','controller','admin')),
  disabled    INTEGER NOT NULL DEFAULT 0,
  lang        TEXT NOT NULL DEFAULT 'en' CHECK (lang IN ('en','hi','mr')),
  created_at  INTEGER NOT NULL,
  created_by  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id          INTEGER PRIMARY KEY,
  token_hash  TEXT NOT NULL UNIQUE,                -- SHA-256 of the cookie value
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created     INTEGER NOT NULL,
  last_seen   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS invites (
  token_hash  TEXT PRIMARY KEY,                    -- SHA-256 of the invite token
  username    TEXT NOT NULL,
  role        TEXT NOT NULL CHECK (role IN ('viewer','controller','admin')),
  expires_at  INTEGER NOT NULL,
  used_at     INTEGER,
  created_by  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS login_attempts (
  ts INTEGER NOT NULL, username TEXT NOT NULL, ip TEXT NOT NULL, ok INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_attempts ON login_attempts (username, ts);
CREATE INDEX IF NOT EXISTS ix_attempts_ip ON login_attempts (ip, ts);

CREATE TABLE IF NOT EXISTS scenarios (
  id              TEXT PRIMARY KEY,
  station_json    TEXT NOT NULL,
  timetable_json  TEXT NOT NULL,
  sha256          TEXT NOT NULL,                   -- of canonical station + timetable
  source          TEXT NOT NULL DEFAULT '',        -- built-in scenario id, or uploaded file sha256 + sheet
  loaded_by       TEXT NOT NULL,
  loaded_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS disruptions (
  id           INTEGER PRIMARY KEY,
  scenario_id  TEXT NOT NULL REFERENCES scenarios(id),
  json         TEXT NOT NULL,                      -- confirmed Delay | Closure
  source_text  TEXT NOT NULL,
  parser_path  TEXT NOT NULL CHECK (parser_path IN ('llm','regex','manual')),
  confirmed_by TEXT NOT NULL,
  confirmed_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS revisions (
  id               TEXT PRIMARY KEY,
  scenario_id      TEXT NOT NULL REFERENCES scenarios(id),
  method           TEXT NOT NULL,
  assignments_json TEXT NOT NULL,
  sha256           TEXT NOT NULL,                  -- of canonical assignments_json
  validation_json  TEXT NOT NULL,
  valid            INTEGER NOT NULL,
  fault_injected   INTEGER NOT NULL DEFAULT 0,
  solver_status    TEXT NOT NULL,
  solve_ms         INTEGER NOT NULL,
  context_json     TEXT NOT NULL DEFAULT '{}',     -- now, disruptions, affected, widened, stages
  created_by       TEXT NOT NULL,
  created_at       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS applied (
  seq          INTEGER PRIMARY KEY,
  scenario_id  TEXT NOT NULL REFERENCES scenarios(id),
  revision_id  TEXT NOT NULL REFERENCES revisions(id),
  applied_by   TEXT NOT NULL,
  applied_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY, ts INTEGER NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
  payload_hash TEXT, summary TEXT, prev_hash TEXT NOT NULL, hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (                 -- feeds the admin dashboard (§34)
  ts INTEGER NOT NULL, kind TEXT NOT NULL, labels TEXT NOT NULL, value REAL NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS ix_events ON events (kind, ts);

-- write-once records
CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON revisions
  BEGIN SELECT RAISE(ABORT, 'revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON revisions
  BEGIN SELECT RAISE(ABORT, 'revisions are immutable'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
