import os
import postgres

from flask import Flask
from flask import request
from flask_httpauth import HTTPBasicAuth

from dotenv import load_dotenv

app = Flask(__name__)
auth = HTTPBasicAuth()


@app.before_first_request
def init_db():
    postgres.init_db()

@auth.verify_password
def verify_password(credential_id, secret):
    if postgres.verify_api_key(credential_id, secret):
        return True
    return None


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
@auth.login_required
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