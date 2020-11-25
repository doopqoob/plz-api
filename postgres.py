

import psycopg2
import psycopg2.extras
import os
import secrets
import socket

from argon2 import PasswordHasher
from uuid import UUID


def connect_db():
    """Return a connection to the database"""
    DB_HOST = os.getenv('DB_HOST')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')

    try:
        db = psycopg2.connect(host=DB_HOST,
                              dbname='plz',
                              user=DB_USER,
                              password=DB_PASSWORD)
    except psycopg2.Error as error:
        print(f'Error connecting to db: {error}')
        return None

    return db


def init_db():
    """Initialize the database"""
    db = connect_db()

    cursor = db.cursor()

    with open('schema.sql', 'r') as sql_file:
        sql = sql_file.read()

        try:
            cursor.execute(sql)
        except psycopg2.Error as error:
            print(f'Error executing SQL: {error}')
            db.close()
            return False

        try:
            db.commit()
        except psycopg2.Error as error:
            print(f'Error committing changes to DB: {error}')
            db.close()
            return False

        db.close()
        return True


def insert(query, data, return_inserted_row_id=False):
    """Insert one row of data into the database, optionally returning the ID of the inserted row"""
    db = connect_db()

    if not db:
        return False

    # Get a cursor for data insertion
    cursor = db.cursor()

    # This must be called to be able to work with UUID objects in postgres for some reason
    psycopg2.extras.register_uuid()

    # Execute the query
    try:
        cursor.execute(query, data)
    except psycopg2.Error as error:
        print(f'Error executing SQL INSERT query: {error}')
        db.close()
        return False

    # Commit changes
    try:
        db.commit()
    except psycopg2.Error as error:
        print(f'Error committing changes to DB: {error}')
        db.close()
        return False

    # Success!
    if return_inserted_row_id:
        # get the id of the newly-created row
        row_id = cursor.fetchone()

        if row_id is None:
            db.close()
            return None

        # close the database connection and return the id
        db.close()
        return row_id[0]
    else:
        db.close()
        return True


def select(query, data=None, real_dict_cursor=False, time_zone=None):
    """Queries the database and returns all rows."""
    db = connect_db()
    if not db:
        return None

    # Get a cursor for data selection
    if real_dict_cursor:
        cursor = db.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cursor = db.cursor()

    # This must be called to be able to work with UUID objects in postgres for some reason
    psycopg2.extras.register_uuid()

    # Set time zone
    if time_zone is not None:
        try:
            tzquery = "SET TIME ZONE %s"
            tzdata = (time_zone,)
            cursor.execute(tzquery, tzdata)
        except psycopg2.Error as error:
            print(f'Error setting time zone: {error}')
            db.close()
            return None

    # Execute the query
    try:
        if data:
            cursor.execute(query, data)
        else:
            cursor.execute(query)
    except psycopg2.Error as error:
        print(f'Error executing SQL query: {error}')
        db.close()
        return None

    # Get all rows from the DB. If there are no rows in the DB, this will return None.
    rows = cursor.fetchall()

    # Close the DB connection and return the rows
    db.close()
    return rows


def get_reverse_dns(ip_address):
    """Gets reverse DNS, if available"""
    try:
        reverse_dns = socket.gethostbyaddr(ip_address)
    except socket.herror as error:
        print(error)
        return None

    if reverse_dns:
        return reverse_dns[0]
    else:
        return None


def add_to_blocklist(ip_address, notes):
    """Adds IP address to blocklist for ever and ever"""

    reverse_dns = get_reverse_dns(ip_address)

    query = "INSERT INTO blocklist (ip_address, reverse_dns, notes) VALUES (%s, %s, %s)"
    data = (ip_address, reverse_dns, notes)
    status = insert(query, data)

    if status:
        return True
    else:
        return False


def is_blocked(ip_address):
    """Returns True if ip_address has been blocked, False otherwise"""

    query = "SELECT * from blocklist WHERE ip_address = %s"
    data = (ip_address,)

    rows = select(query, data)
    if rows:
        return True
    else:
        return False


def is_rate_limited(ip_address):
    """Returns True if ip_address has hit its rate limits, False otherwise"""

    # Has the ip address submitted more than three tickets in the last minute?
    query = "SELECT COUNT(ticket_id) FROM ticket " \
            "WHERE requested_at >= (now() - INTERVAL '1 minute') AND ip_address = %s"
    data = (ip_address,)

    row_count = select(query, data)
    row_count = row_count[0][0]

    if row_count >= 3:
        return True

    # Has the ip address submitted more than ten tickets in the last hour?
    query = "SELECT COUNT(ticket_id) FROM ticket " \
            "WHERE requested_at >= (now() - INTERVAL '1 hour') AND ip_address = %s"
    data = (ip_address,)

    row_count = select(query, data)
    row_count = row_count[0][0]

    if row_count >= 10:
        return True

    # Has the ip address submitted more than twenty tickets in the last day?
    query = "SELECT COUNT(ticket_id) FROM ticket " \
            "WHERE requested_at >= (now() - INTERVAL '1 day') AND ip_address = %s"
    data = (ip_address,)

    row_count = select(query, data)
    row_count = row_count[0][0]

    if row_count >= 20:
        return True

    # Congratulations! you passed the test
    return False


def create_api_key():
    """Creates a new API key and returns it to the user."""
    # Create a new secret and hash it
    pass_hasher = PasswordHasher()
    secret = secrets.token_urlsafe(64)
    hash = pass_hasher.hash(secret)

    # verify the secret
    if not pass_hasher.verify(hash, secret):
        return False

    if pass_hasher.check_needs_rehash(hash):
        return False

    # insert the secret into the DB
    query = "INSERT INTO credential (password_hash) VALUES (%s) RETURNING credential_id"
    data = (hash,)

    credential_id = insert(query, data, return_inserted_row_id=True)

    if not credential_id:
        return False

    return {'credential_id': credential_id, 'secret': secret}


def verify_api_key(credential_id, secret):
    """Verify a given API key"""

    # check that credential and secret are provided
    if not credential_id:
        return False

    if not secret:
        return False

    # Prepare database query
    query = "SELECT * FROM credential WHERE credential_id = %s AND active = true"
    data = (credential_id,)

    # Execute database query
    rows = select(query, data, real_dict_cursor=True)

    # Ensure a row came back
    if not rows:
        return False

    # Verify password hash
    hash = rows[0]['password_hash']
    pass_hasher = PasswordHasher()

    if not pass_hasher.verify(hash, secret):
        return False

    return True


def create_crate(crate_name):
    """Creates a new crate in which to file songs"""
    if crate_name is None:
        return None

    query = "SELECT crate_id FROM crate WHERE crate_name = %s"
    data = (crate_name,)
    crate_id = select(query, data)

    if crate_id:
        return crate_id[0]

    query = "INSERT INTO crate (crate_name) VALUES (%s) RETURNING crate_id"
    crate_id = insert(query, data, return_inserted_row_id=True)

    if crate_id:
        return crate_id
    else:
        print("something went wrong creating a crate")
        return None


def create_show(show_name):
    """Creates a new show, which is really just a collection of crates"""
    if show_name is None:
        return None

    query = "INSERT INTO show (show_name) VALUES (%s) RETURNING show_id"
    data = (show_name,)
    show_id = insert(query, data, return_inserted_row_id=True)

    if show_id:
        return show_id
    else:
        print("something went wrong adding a show")
        return None


def get_shows():
    """Get a list of all shows from the database"""
    query = "SELECT show_id,show_name FROM show WHERE active = true ORDER BY show_name"
    rows = select(query)

    if rows:
        return rows
    else:
        print("No active shows in DB")
        return None


def get_time_zones():
    """Get a list of all time zones from the database"""
    query = "SELECT name FROM pg_timezone_names ORDER BY name"
    rows = select(query)

    if rows:
        return rows
    else:
        print("No time zone names on the database?????? Something is seriously wrong.")
        return None



def get_crates(show_id=None):
    """Gets a list of crates associated with a show. If no show is given, gets all crates."""
    if isinstance(show_id, int):
        query = "SELECT * FROM show_crate INNER JOIN crate on show_crate.crate_id = crate.crate_id WHERE show_id = %s "
        data = (show_id,)
        rows = select(query, data, real_dict_cursor=True)
        crates = []
        for row in rows:
            crates.append((row['crate_id'],row['crate_name']))
        return crates
    else:
        query = "SELECT crate_id,crate_name FROM crate"
        crates = select(query)
        return crates


def associate_crates(show_id, crate_ids):
    """Associate any number of crates with a show."""
    query = "INSERT INTO show_crate (show_id, crate_id) VALUES (%s, %s)"

    if crate_ids is not type(list):
        return False

    for crate_id in crate_ids:
        data = (show_id, crate_id)
        result = insert(query, data)
        if result is not True:
            return False

    return True


def create_artist(artist_name):
    """Creates a new crate in which to file songs"""
    if artist_name is None:
        return None

    query = "SELECT artist_id FROM artist WHERE artist_name = %s"
    data = (artist_name,)
    artist_id = select(query, data)

    if artist_id:
        return artist_id[0]

    query = "INSERT INTO artist (artist_name) VALUES (%s) RETURNING artist_id"

    artist_id = insert(query, data, return_inserted_row_id=True)

    if artist_id:
        return artist_id
    else:
        print("something went wrong creating/inserting an artist")
        return None


def insert_song_metadata(song_metadata):
    """Inserts a song's metadata into the DB"""
    if not song_metadata:
        return None

    # get the id of the crate named in the song metadata
    # (or create it if it doesn't exist)
    crate_id = create_crate(song_metadata['crate_name'])

    if not crate_id:
        return None

    # do the same for artist_id
    artist_id = create_artist(song_metadata['artist'])

    if not artist_id:
        return None

    # hash the song audio (but not the metadata)
    song_hash = bytes.fromhex(song_metadata['hash'])

    # Insert values into song, unless there's already a song with that hash, in which case update metadata for
    # the song with the given hash
    query = "INSERT INTO song (crate_id, hash, artist_id, song_title, song_tempo, song_key) " \
            "VALUES (%s, %s, %s, %s, %s, %s) " \
            "ON CONFLICT (hash) " \
            "DO UPDATE SET artist_id = %s, song_title = %s, song_tempo = %s, song_key = %s " \
            "RETURNING song_id"

    # data fields have to match every %s in order, which is why you see some values twice
    data = (crate_id,
            song_hash,
            artist_id,
            song_metadata['title'],
            song_metadata['tempo'],
            song_metadata['key'],
            artist_id,
            song_metadata['title'],
            song_metadata['tempo'],
            song_metadata['key'])

    song_id = insert(query, data, return_inserted_row_id=True)
    return song_id


def get_show_artists(show_id):
    """Get all artists associated with a show"""
    if not isinstance(show_id, int):
        return None

    query = "SELECT artist_id, artist_name, appearances FROM artist_appearance_count WHERE show_id = %s"
    data = (show_id,)
    rows = select(query, data)

    if not rows:
        return None

    return rows


def get_show_songs(show_id, artist_id=None):
    """Get all songs for a show associated with a specific artist. If no artist is given, get all songs for a show."""
    if not isinstance(show_id, int):
        return None

    if artist_id:
        query = "SELECT song.song_id, song.song_title, artist.artist_name FROM show_crate " \
                "INNER JOIN song ON song.crate_id = show_crate.crate_id " \
                "INNER JOIN artist ON song.artist_id = artist.artist_id " \
                "WHERE show_crate.show_id = %s AND song.artist_id = %s " \
                "ORDER BY song.song_title "
        data = (show_id,artist_id)
    else:
        query = "SELECT song.song_id, song.song_title, artist.artist_name FROM show_crate " \
                "INNER JOIN song ON song.crate_id = show_crate.crate_id " \
                "INNER JOIN artist ON song.artist_id = artist.artist_id " \
                "WHERE show_crate.show_id = %s " \
                "ORDER BY song.song_title "
        data = (show_id,)

    rows = select(query, data)

    if rows:
        return rows
    else:
        return None


def add_selected_request(form_data, ip_address):
    """Add a request where the user has selected a song from a list"""

    # Validate input and add to database
    if 'show_id' in form_data:
        try:
            show_id = int(form_data['show_id'])
        except ValueError as e:
            print(e)
            return False
    else:
        return False

    if 'song_id' in form_data:
        try:
            song_id = UUID(form_data['song_id'])
        except ValueError as e:
            print(e)
            return False
    else:
        return False

    if 'submitted_by' in form_data:
        submitted_by = form_data['submitted_by']
        if len(submitted_by) == 0:
            return False
        elif len(submitted_by) > 128:
            submitted_by = submitted_by[:128]
    else:
        return False

    if 'notes' in form_data:
        notes = form_data['notes']
        if len(notes) > 512:
            notes = notes[:512]
    else:
        notes = None

    reverse_dns = get_reverse_dns(ip_address)

    query = "INSERT INTO ticket (show_id, requested_by, ip_address, reverse_dns, notes) VALUES (%s, %s, %s, %s, %s) RETURNING ticket_id"
    data = (show_id, submitted_by, ip_address, reverse_dns, notes)

    ticket_id = insert(query, data, return_inserted_row_id=True)

    if ticket_id is None:
        return False

    query = "INSERT INTO selected_request (ticket_id, song_id) VALUES (%s, %s)"
    data = (ticket_id, song_id)

    result = insert(query, data)

    if result:
        return ticket_id
    else:
        return False


def add_freeform_request(form_data, ip_address):
    """Add a request where the user has entered artist/title manually"""

    if 'show_id' in form_data:
        try:
            show_id = int(form_data['show_id'])
        except ValueError as e:
            print(e)
            return False
    else:
        return False

    if 'artist_name' in form_data:
        artist_name = form_data['artist_name']
        if len(artist_name) == 0:
            return False
        elif len(artist_name) > 128:
            artist_name = artist_name[:128]
    else:
        return False

    if 'song_title' in form_data:
        song_title = form_data['song_title']
        if len(song_title) == 0:
            return False
        elif len(song_title) > 256:
            song_title = song_title[:256]
    else:
        return False

    if 'submitted_by' in form_data:
        submitted_by = form_data['submitted_by']
        if len(submitted_by) == 0:
            return False
        elif len(submitted_by) > 128:
            submitted_by = submitted_by[:128]
    else:
        return False

    if 'notes' in form_data:
        notes = form_data['notes']
        if len(notes) > 512:
            notes = notes[:512]
    else:
        notes = None

    reverse_dns = get_reverse_dns(ip_address)

    query = "INSERT INTO ticket (show_id, requested_by, ip_address, reverse_dns, notes) VALUES (%s, %s, %s, %s, %s) RETURNING ticket_id"
    data = (show_id, submitted_by, ip_address, reverse_dns, notes)
    ticket_id = insert(query, data, return_inserted_row_id=True)

    if ticket_id is None:
        return False

    query = "INSERT INTO freeform_request (ticket_id, artist_name, song_title) VALUES (%s, %s, %s)"
    data = (ticket_id, artist_name, song_title)

    result = insert(query, data)

    if result:
        return ticket_id
    else:
        return False


def get_unprinted_tickets(time_zone):
    """Gets unprinted tickets"""

    query = "SELECT " \
            "request.*, " \
            "to_char(requested_at AT TIME ZONE %s, 'YYYY-MM-DD HH24:MI:SS') AS requested_at, " \
            "pg_timezone_names.abbrev AS tz_abbrev " \
            "FROM request " \
            "INNER JOIN pg_timezone_names ON %s = pg_timezone_names.name " \
            "WHERE printed = false ORDER BY request.requested_at"
    data = (time_zone, time_zone)
    rows = select(query, data, real_dict_cursor=True)

    if rows is None:
        return None

    if len(rows) == 0:
        return None

    return rows


def get_ticket(ticket_id, time_zone):
    """Gets a specific ticket by ID number, given in terms of time_zone."""
    try:
        ticket_id = UUID(ticket_id)
    except ValueError as e:
        print(e)
        return False

    query = "SELECT " \
            "request.*, " \
            "to_char(requested_at AT TIME ZONE %s, 'YYYY-MM-DD HH24:MI:SS') AS requested_at, " \
            "pg_timezone_names.abbrev AS tz_abbrev " \
            "FROM request " \
            "INNER JOIN pg_timezone_names ON %s = pg_timezone_names.name " \
            "WHERE ticket_id = %s"
    data = (time_zone, time_zone, ticket_id)
    result = select(query, data, real_dict_cursor=True)

    if result:
        return result[0]
    else:
        return None


def get_tickets(time_zone, time_interval=None, show_id=None, ip_address=None, user_name=None):
    """
    Gets all tickets, given in terms of time_zone.
    If time_interval is given, tickets between then and now are retrieved.
    """

    # Build the query
    query = "SELECT " \
            "request.*, " \
            "to_char(requested_at AT TIME ZONE %s, 'YYYY-MM-DD HH24:MI:SS') AS requested_at, " \
            "pg_timezone_names.abbrev AS tz_abbrev " \
            "FROM request " \
            "INNER JOIN pg_timezone_names ON %s = pg_timezone_names.name "

    filters = []
    data = [time_zone, time_zone]

    if time_interval is not None:
        filters.append("requested_at >= (now() - INTERVAL %s) ")
        data.append(time_interval)

    if show_id is not None:
        filters.append("show_id = %s ")
        data.append(show_id)

    if ip_address is not None:
        filters.append("ip_address = %s ")
        data.append(ip_address)

    if user_name is not None:
        filters.append("requested_by = %s ")
        data.append(user_name)

    if filters:
        filters_string = "AND "
        query += "WHERE " + filters_string.join(filters)
        print(query)

    query += "ORDER BY request.requested_at DESC"
    data = tuple(data)

    # run the query
    result = select(query, data, real_dict_cursor=True)

    if result:
        return result
    else:
        return None


def mark_ticket_as_printed(ticket_id):
    """Marks a ticket as printed"""
    try:
        ticket_id = UUID(ticket_id)
    except ValueError as e:
        print(e)
        return False

    query = "UPDATE ticket SET printed = true WHERE ticket_id = %s"
    data = (ticket_id,)

    result = insert(query, data)

    return result
