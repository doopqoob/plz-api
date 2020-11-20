import psycopg2
import psycopg2.extras
import os
import secrets

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
        row_id = cursor.fetchone()[0]

        # close the database connection and return the id
        db.close()
        return row_id
    else:
        db.close()
        return True


def select(query, data=None, real_dict_cursor=False):
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

    query = "INSERT INTO crate (crate_name) VALUES (%s) RETURNING crate_id"
    data = (crate_name,)
    crate_id = insert(query, data, return_inserted_row_id=True)

    if crate_id:
        return crate_id
    else:
        print("something went wrong creating a crate")
        return None


def get_crate_id(crate_name):
    if crate_name is None:
        return None

    query = "SELECT crate_id FROM crate WHERE crate_name = %s"
    data = (crate_name,)

    rows = select(query, data, real_dict_cursor=True)

    if not rows:
        return None

    if rows[0]['crate_id']:
        return rows[0]['crate_id']
    else:
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


def insert_song_metadata(song_metadata):
    """Inserts a song's metadata into the DB"""

    # get the id of the crate named in the song metadata
    crate_id = get_crate_id(song_metadata['crate_name'])

    # If the crate doesn't exist yet, create it
    if not crate_id:
        crate_id = create_crate(song_metadata['crate_name'])

        if not crate_id:
            return

    song_hash = bytes.fromhex(song_metadata['hash'])

    # Insert values into song, unless there's already a song with that hash, in which case update metadata for
    # the song with the given hash
    query = "INSERT INTO song (crate_id, hash, artist, title, tempo, key) " \
            "VALUES (%s, %s, %s, %s, %s, %s) " \
            "ON CONFLICT (hash) " \
            "DO UPDATE SET artist = %s, title = %s, tempo = %s, key = %s " \
            "RETURNING song_id"


    # data fields have to match every %s in order, which is why you see some values twice
    data = (crate_id,
            song_hash,
            song_metadata['artist'],
            song_metadata['title'],
            song_metadata['tempo'],
            song_metadata['key'],
            song_metadata['artist'],
            song_metadata['title'],
            song_metadata['tempo'],
            song_metadata['key'])

    song_id = insert(query, data, return_inserted_row_id=True)
    return song_id
