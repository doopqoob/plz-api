CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS credential (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username text UNIQUE NOT NULL,
    password_hash text NOT NULL
);

CREATE TABLE IF NOT EXISTS crate (
    crate_id int NOT NULL GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
    crate_name text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS show (
    show_id int NOT NULL GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
    show_name text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS show_crate (
    show_id int REFERENCES show(show_id) ON DELETE CASCADE,
    crate_id int REFERENCES crate(crate_id) ON DELETE CASCADE,
    PRIMARY KEY(show_id, crate_id)
);

CREATE TABLE IF NOT EXISTS song (
    song_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    crate_id int NOT NULL REFERENCES crate(crate_id) ON DELETE CASCADE,
    hash bytea UNIQUE NOT NULL,
    artist text NOT NULL,
    title text NOT NULL,
    tempo smallint NOT NULL,
    key text NOT NULL
);

CREATE TABLE IF NOT EXISTS ticket (
    ticket_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_at timestamptz NOT NULL DEFAULT now(),
    requested_by text NOT NULL,
    printed boolean NOT NULL DEFAULT FALSE,
    notes text
);

CREATE TABLE IF NOT EXISTS freeform_request (
    ticket_id uuid PRIMARY KEY REFERENCES ticket(ticket_id) ON DELETE CASCADE,
    artist text NOT NULL,
    title text NOT NULL
);

CREATE TABLE IF NOT EXISTS selected_request (
    ticket_id uuid PRIMARY KEY REFERENCES ticket(ticket_id)  ON DELETE CASCADE,
    song_id uuid NOT NULL REFERENCES song(song_id) ON DELETE CASCADE
);

CREATE VIEW request AS
    SELECT ticket_id,
           'freeform' as type,
           null,
           artist,
           title,
           null,
           null
    FROM freeform_request
UNION
    SELECT ticket_id,
           'selected' as type,
           selected_request.song_id,
           artist,
           title,
           tempo,
           key
    FROM selected_request
        INNER JOIN song on selected_request.song_id = song.song_id;