import os
import postgres

from flask import Flask
from flask import request
from flask_httpauth import HTTPBasicAuth
from uuid import UUID

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


@app.route('/api/v2/')
def hello_world():
    return 'Hello World!'


@app.route('/api/v2/api_key')
def new_api_key():
    """Get a new API key"""
    credentials = postgres.create_api_key()

    if not credentials:
        message = {"message": "Something went wrong getting an API key"}
        return message, 500

    return {"credentials": credentials}, 200

@app.route('/api/v2/add_song', methods=['POST'])
@auth.login_required
def add_song():
    """Add a song to the database"""
    # Get the JSON from the request and send it to the postgres module. If everything is successful, the
    # postgres module will return the ID of the newly-created song entry in the DB.
    song_id = postgres.insert_song_metadata(request.get_json())

    if not song_id:
        message = {"message": "Something went wrong adding your song"}
        return message, 500

    # Return the new quote ID
    message = {"id": song_id}
    return message, 201


@app.route('/api/v2/add_show', methods=['POST'])
@auth.login_required
def add_show():
    """Add a show to the database"""
    show_id = postgres.create_show(request.get_json()['show_name'])

    if not show_id:
        message = {"message": "Something went wrong adding your show"}
        return message, 500

    message = {"id": show_id}
    return message, 201


@app.route('/api/v2/get_shows')
def get_shows():
    """Get a list of all active shows"""
    shows = postgres.get_shows()

    if not shows:
        message = {"message": "No active shows in DB"}
        return message, 500

    message = {"shows": shows}
    return message, 200


@app.route('/api/v2/get_crates')
def get_crates():
    """Get a list of all crates associated with a show"""
    if request.args.get('show_id'):
        show_id = int(request.args.get('show_id'))
        crates = postgres.get_crates(show_id)
    else:
        crates = postgres.get_crates()

    if not crates:
        message = {"message": "No crates associated with given show_id."}
        return message, 500

    message = {"crates": crates}
    return message, 200


@app.route('/api/v2/associate_crates', methods=['POST'])
@auth.login_required
def associate_crates():
    """Associate a show with one or more crates. Any number of crates can be shared by any number of shows."""
    association = request.get_json()

    result = postgres.associate_crates(association['show_id'],association['crate_ids'])

    if result is False:
        message = {"message": "Something went wrong associating your crates"}
        return message, 500

    if result is True:
        message = {"message": "Crates associated successfully!"}
        return message, 201

    return 500


@app.route('/api/v2/get_show_artists')
def get_show_artists():
    """Get all artists in the DB for a given show"""
    if request.args.get('show_id') is None:
        message = {"message": "No show provided"}
        return message, 400

    artists = postgres.get_show_artists(int(request.args.get('show_id')))

    if artists is None:
        message = {"message": "No artists found"}
        return message, 404

    message = {"artists": artists}
    return message, 200


@app.route('/api/v2/get_show_songs')
def get_show_songs():
    """Get songs for a show, optionally specifying an artist ID"""
    if request.args.get('show_id') is None:
        message = {"message": "No show provided"}
        return message, 400

    show_id = int(request.args.get('show_id'))

    if request.args.get('artist_id'):
        artist_id = UUID(request.args.get('artist_id'))
    else:
        artist_id = None

    songs = postgres.get_show_songs(show_id, artist_id)

    if songs is None:
        message = {"message": "No songs found"}
        return message, 404

    message = {"songs": songs}
    return message, 200


@app.route('/api/v2/add_selected_request', methods=['POST'])
def add_selected_request():
    """Add a request the user has selected from a list"""
    form_data = request.get_json()

    if 'email' in form_data:
        if form_data['email']:
            message = {"message": "Success!"}
            return message, 201

    # Is sender's ip blocklisted?
    if postgres.is_blocked(request.remote_addr):
        message = {"message": "Something went wrong inserting your data"}
        return message, 500

    # Is sender's ip address rate limited?
    if postgres.is_rate_limited(request.remote_addr):
        message = {"message": "Rate-limited"}
        return message, 401

    ticket_id = postgres.add_selected_request(form_data, request.remote_addr)
    if ticket_id:
        message = {"ticket_id": ticket_id}
        return message, 201
    else:
        message = {"message": "Something went wrong inserting your data"}
        return message, 500


@app.route('/api/v2/add_freeform_request', methods=['POST'])
def add_freeform_request():
    """Add a request the user has entered manually"""
    form_data = request.get_json()

    if 'email' in form_data:
        if form_data['email']:
            message = {"message": "Success!"}
            return message, 201

    # Is sender's ip blocklisted?
    if postgres.is_blocked(request.remote_addr):
        message = {"message": "Something went wrong inserting your data"}
        return message, 500

    # Is sender's ip address rate limited?
    if postgres.is_rate_limited(request.remote_addr):
        message = {"message": "Rate-limited"}
        return message, 401

    ticket_id = postgres.add_freeform_request(form_data, request.remote_addr)
    if ticket_id:
        message = {"ticket_id": ticket_id}
        return message, 201
    else:
        message = {"message": "Something went wrong inserting your data"}
        return message, 500


@app.route('/api/v2/download_unprinted_tickets')
@auth.login_required
def download_unprinted_tickets():
    """Download unprinted tickets"""
    time_zone = request.args.get('time_zone')

    ticket_list = postgres.get_unprinted_tickets(time_zone)

    if ticket_list is None:
        return {"message": "No unprinted tickets"}, 404

    message = {"tickets": ticket_list}
    return message, 200


@app.route('/api/v2/download_ticket')
@auth.login_required
def download_ticket():
    """Download unprinted tickets"""
    ticket_id = request.args.get('ticket_id')
    if ticket_id is None:
        return {"message": "Missing ticket ID"}, 400

    time_zone = request.args.get('time_zone')

    if time_zone is None:
        time_zone = "Etc/UTC"

    ticket = postgres.get_ticket(ticket_id, time_zone)

    if ticket is None:
        return {"message": "No ticket by that ID"}, 404

    message = {"ticket": ticket}
    return message, 200


@app.route('/api/v2/download_tickets')
@auth.login_required
def download_tickets():
    """Download all tickets"""
    time_zone = request.args.get('time_zone')

    if time_zone is None:
        time_zone = "Etc/UTC"

    time_interval = request.args.get('time_interval')

    show_id = None
    if request.args.get('show_id'):
        show_id = int(request.args.get('show_id'))

    tickets = postgres.get_tickets(time_zone, time_interval=time_interval, show_id=show_id)

    if tickets is None:
        return {"message": "No tickets in DB matching selected criteria!"}, 404

    message = {"tickets": tickets}
    return message, 200


@app.route('/api/v2/mark_ticket_printed')
@auth.login_required
def mark_ticket_printed():
    if request.args.get('ticket_id') is None:
        message = {"message": "No ticket ID given"}
        return message, 400

    result = postgres.mark_ticket_as_printed(request.args.get('ticket_id'))

    if result:
        return {"message": "success!"}, 200
    else:
        return {"message": "something went wrong!"}, 500


@app.route('/api/v2/block_ip', methods=['POST'])
@auth.login_required
def block_ip():
    form_data = request.get_json()

    if 'ip_address' not in form_data:
        message = {"message": "No IP address given"}
        return message, 400

    if form_data['ip_address'] is None:
        message = {"message": "No IP address given"}
        return message, 400

    if 'notes' not in form_data:
        notes = None
    else:
        notes = form_data['notes']

    result = postgres.add_to_blocklist(form_data['ip_address'], notes)

    if result:
        return {"message": "success!"}, 201
    else:
        return {"message": "something went wrong blocking an ip address"}, 500