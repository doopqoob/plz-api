import os
import postgres

from flask import Flask
from flask import request

from dotenv import load_dotenv

app = Flask(__name__)


@app.before_first_request
def init_db():
    postgres.init_db()


@app.route('/')
def hello_world():
    return 'Hello World!'


@app.route('/api/key')
def new_api_key():
    """Get a new API key"""
    credentials = postgres.create_api_key()

    if not credentials:
        message = {"message": "Something went wrong getting an API key"}
        return message, 500

    return credentials, 200

@app.route('/add/song', methods=['POST'])
def add_song():
    """Add a song to the database"""
    # Get the JSON from the request and send it to the postgres module. If everything is successful, the
    # postgres module will return the ID of the newly-created song entry in the DB.
    id = postgres.insert_song_metadata(request.get_json())

    if not id:
        message = {"message": "Something went wrong adding your song"}
        return message, 500

    # Return the new quote ID
    message = {"id": id}
    return message, 201