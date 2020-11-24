CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS credential (
    credential_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    password_hash text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    active bool DEFAULT false
);

CREATE TABLE IF NOT EXISTS show (
    show_id int NOT NULL PRIMARY KEY GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
    show_name text UNIQUE NOT NULL,
    active bool DEFAULT true
);

CREATE TABLE IF NOT EXISTS crate (
    crate_id int NOT NULL PRIMARY KEY GENERATED ALWAYS AS IDENTITY (START WITH 1 INCREMENT BY 1),
    crate_name text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS show_crate (
    show_id int REFERENCES show(show_id) ON DELETE CASCADE,
    crate_id int REFERENCES crate(crate_id) ON DELETE CASCADE,
    PRIMARY KEY(show_id, crate_id)
);

CREATE TABLE IF NOT EXISTS artist (
    artist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    artist_name text UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS song (
    song_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    crate_id int NOT NULL REFERENCES crate(crate_id) ON DELETE CASCADE,
    hash bytea UNIQUE NOT NULL,
    artist_id uuid NOT NULL REFERENCES artist(artist_id) ON DELETE CASCADE,
    song_title text NOT NULL,
    song_tempo smallint,
    song_key text
);

CREATE TABLE IF NOT EXISTS ticket (
    ticket_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    show_id int NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now(),
    requested_by text NOT NULL,
    ip_address inet NOT NULL,
    reverse_dns text,
    printed boolean NOT NULL DEFAULT FALSE,
    notes text
);

CREATE TABLE IF NOT EXISTS freeform_request (
    ticket_id uuid PRIMARY KEY REFERENCES ticket(ticket_id) ON DELETE CASCADE,
    artist_name text NOT NULL,
    song_title text NOT NULL
);

CREATE TABLE IF NOT EXISTS selected_request (
    ticket_id uuid PRIMARY KEY REFERENCES ticket(ticket_id)  ON DELETE CASCADE,
    song_id uuid NOT NULL REFERENCES song(song_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS blocklist (
    ip_address inet PRIMARY KEY,
    blocked_at timestamptz NOT NULL DEFAULT now(),
    reverse_dns text,
    notes text
);

CREATE OR REPLACE VIEW artist_appearance_count AS
    SELECT show_id, artist.artist_id, artist.artist_name, COUNT(artist.artist_id) as appearances
    FROM show_crate
    INNER JOIN song ON show_crate.crate_id = song.crate_id
    INNER JOIN artist ON song.artist_id = artist.artist_id
    GROUP BY show_id, artist.artist_id, artist_name
    ORDER BY artist_name;

CREATE OR REPLACE VIEW request AS
    SELECT freeform_request.ticket_id,
           'freeform' as type,
           requested_at,
           ticket.show_id,
           show_name,
           artist_name,
           song_title,
           null as song_tempo,
           null as song_key,
           requested_by,
           notes,
           ip_address,
           reverse_dns,
           printed
    FROM freeform_request
    INNER JOIN ticket ON freeform_request.ticket_id = ticket.ticket_id
    INNER JOIN show ON ticket.show_id = show.show_id
UNION
    SELECT selected_request.ticket_id,
           'selected' as type,
           requested_at,
           ticket.show_id,
           show_name,
           artist_name,
           song_title,
           song_tempo,
           song_key,
           requested_by,
           notes,
           ip_address,
           reverse_dns,
           printed
    FROM selected_request
        INNER JOIN song ON selected_request.song_id = song.song_id
        INNER JOIN artist ON song.artist_id = artist.artist_id
        INNER JOIN ticket ON selected_request.ticket_id = ticket.ticket_id
        INNER JOIN show ON ticket.show_id = show.show_id;
