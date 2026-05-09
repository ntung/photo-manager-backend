import hashlib
import json
import logging
import math
import os
import pathlib
import pprint
import random
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from functools import wraps
from logging.config import dictConfig

import bson
import bson.json_util
import pymongo
import pytz
import requests
from bson import ObjectId
from dotenv import load_dotenv
from flask import Flask, Response
from flask import jsonify, render_template, request, url_for
from flask import redirect, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
from jinja2 import FileSystemBytecodeCache
# from gunicorn.sock import ssl_context
from pymongo import MongoClient, ReturnDocument
from slugify import slugify

from migration_framework.runner import MigrationRunner
from .utils import PhotoManager

load_dotenv()  # loads variables from .env into environment

TMP_BM = tempfile.gettempdir() + "/photo-manager/upload"
os.makedirs(TMP_BM, exist_ok=True)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', TMP_BM)
db_port_str = os.getenv("DB_PORT")
if db_port_str is None:
    raise RuntimeError("DB_PORT is not set")
db_port = int(db_port_str)
client = MongoClient(os.getenv("DB_HOST", "localhost"), db_port)
db_host = os.getenv("DB_HOST")
if db_host is None:
    raise RuntimeError("DB_HOST is not set")
client = MongoClient(db_host, db_port)
db_name = os.getenv("DB_NAME", "photodb")
db = client[db_name]
todos = db.todos

TZ_LONDON = pytz.timezone("Europe/London")

"""
TODO LIST
     0/ Calculate aaaa, aaab, aaac... submission folders
Done 1/ Delete photos and albums: will delete physical photos and albums too.
Prog 2/ Add/edit,remove photos to/out albums
     3/ Improve the views by allowing zoom, click open a single photo
Prog 4/ Improve adding photos: add tags, hashtags, keywords, etc.
     5/ Loading more data when scrolling or pagination, do not load all once.
Done 6/ View photos by albums
Done 7/ Add/Edit an album: edit title, description; add more photos...
Done 8/ Check md5 to avoid repeating images
     9/ Favourite/Highlight
     10/ Set album profile/cover photo
Prog 11/ Sort photos by title, data uploaded, shuffle photos
Done 12/ After Save photo to album, update "In Albums:"
Done 13/ handle the date_uploaded and date_modified using
         datetime.strftime('%Y-%m-%d %H:%M:%S')
Done 14/ uuid for photos uploaded via browsing files
Done 15/ nên hiển thị photos của 1 album theo thứ tự ngược lại:
         [1, 2, 3] => display 3, 2, 1
     16/ Khi sort thì nên nhớ view style hiện tại là gallery hay list
"""

dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    },
    "handlers": {
        "wsgi": {
            "class": "logging.StreamHandler",
            "stream": "ext://flask.logging.wsgi_errors_stream",
            "formatter": "default"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": "logs/app.log",
            "mode": "a",
            "maxBytes": 1024 * 1024 * 10,
            "backupCount": 5,
            "formatter": "default"
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["wsgi", "file"]
    }
})

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type: application/json'
socketio = SocketIO(app)
bcc = FileSystemBytecodeCache('/tmp/jinja_cache', '%s.cache')
app.jinja_env.bytecode_cache = bcc
API_SVR = os.environ.get('API_SERVER')
pm_init = PhotoManager.InitPM(UPLOAD_FOLDER, "aaaa")
submission_folders = pm_init.submission_folder_dict()
nb_downloads = 0


@app.cli.command()
def migrate():
    """
    Migrates to the latest version
    """

    runner = MigrationRunner(
        uri=os.getenv("MONGODB_URI"),
        db_name=os.getenv("DB_NAME"),
    )
    runner.run()


def infer_submission_folder():
    location = pm_init.infer_current_submission_folder(submission_folders)
    if location in submission_folders:
        submission_folders[location] += 1
    else:
        submission_folders[location] = 1
    app.logger.info("current submission folder: %s", location)
    return location


# https://www.linkedin.com/advice/0/what-some-best-practices-managing-flask-session-expiration
# https://www.maskaravivek.com/post/how-to-add-http-cachecontrol-headers-in-flask/
# https://stackoverflow.com/questions/704561/ns-binding-aborted-shown-in-firefox-with-httpfox
def do_cache(minutes=5, content_type='application/json; charset=utf-8'):
    """ Flask decorator that allows set Expire and Cache headers. """

    def fwrap(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            r = f(*args, **kwargs)
            then = datetime.now() + timedelta(minutes=minutes)
            rsp = Response(r, content_type=content_type)
            v = then.strftime("%a, %d %b %Y %H:%M:%S GMT")
            rsp.headers.add('Expires', v)
            v = f'public,max-age={int(60 * minutes)}'
            rsp.headers.add('Cache-Control', v)
            return rsp

        return wrapped_f

    return fwrap


@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('index.html')


@app.route('/photo/todo-list', methods=('GET', 'POST'))
def photo_todo_list():
    app.logger.info("You've accessed TODO List")
    if request.method == 'POST':
        content = request.form['content']
        degree = request.form['degree']
        todos.insert_one({'content': content, 'degree': degree})
        return redirect(url_for('todo_list'))

    all_todos = todos.find()
    return render_template('todo-list.html', todos=all_todos)


def save_metadata(_sub_folder, _filename, _title, _desc, _courtesy, _hash_md5):
    if not _title:
        _title = "Untitled"
    if not _desc:
        _desc = _filename
    if not _courtesy:
        _courtesy = "Unknown"
    db.photos.insert_one({'folder': _sub_folder,
                          'filename': _filename,
                          'title': _title,
                          'description': _desc,
                          'courtesy': _courtesy,
                          'date_uploaded': datetime.now(TZ_LONDON),
                          'date_modified': datetime.now(TZ_LONDON),
                          'hash_md5': _hash_md5})


@app.route('/album/add', methods=('GET', 'POST'))
def album_add():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    _albums = request_json['albums']
    _photos = request_json['photos']
    for photo_id in _photos:
        for album in _albums:
            db.albums.update_one(
                {'path': album['path']},
                {
                    '$addToSet': {'photos': ObjectId(photo_id)},
                    '$set': {'date_modified': datetime.now(TZ_LONDON)},
                },
                upsert=False
            )

    result = {"message": "Building the service"}
    return json.dumps(result)


@app.route('/photo/albums', methods=('GET', 'POST'))
def photo_albums():
    app.logger.info("You've accessed photo albums")
    view = 'photo-albums.html'
    if request.method == 'POST':
        file = request.files['cover']
        if file.content_length > 0:
            app.logger.info("TODO: implement to store this photo")
        if request.form['title'] is not None or not request.form['title']:
            title = request.form['title']
        else:
            title = "Untitled"
        desc = request.form['description']
        description = desc if desc else 'My new album'
        if title == "Untitled":
            all_untitled_albums = db.albums.find({
                "title": {'$regex': '^Untitled'}}
            ).limit(1).sort('title', pymongo.ASCENDING)
            if all_untitled_albums is None:
                title = "Untitled 001"
            else:
                for album in all_untitled_albums:
                    app.logger.info(album['title'])
        app.logger.info("%s\t%s", title, description)

        if not title:
            # stop creating untitled album
            return redirect(url_for('photo_albums'))

        path = slugify(title)
        if db.albums.find_one({'path': path}):
            app.logger.info("Album '%s' already exists (path=%s)", title, path)
            return redirect(url_for('photo_albums') + '?error=Album+already+exists')
        r = db.albums.insert_one({
            'path': path, 'title': title, 'description': description,
            'photos': [],
            'date_created': datetime.now(TZ_LONDON),
            'date_modified': datetime.now(TZ_LONDON)
        })
        app.logger.info("Inserted a new record to db.photos %s", r)
        return redirect(url_for('photo_albums'))
    if request.method == 'GET':
        all_albums = db.albums.find()
        _albums = bson.json_util.dumps(all_albums)
        _albums = bson.json_util.loads(_albums)
        nb_photos_dict = {}
        for album in _albums:
            nb_photos_dict[album['path']] = len(album['photos'])

        sort = request.args.get('sort')
        # if sort is None:
        #     sort = "date_modified;down"
        sorted_albums = _albums

        if sort is not None:
            s_opts = sort.split(";")
            sort_field = s_opts[0]
            sort_direction = s_opts[1]
            fields = [
                "title", "amount_photos", "date_created", "date_modified"
            ]
            if sort_field in fields:
                is_reverse = sort_direction != "down"
                if sort_field == "amount_photos":
                    sorted_albums = sorted(_albums,
                                           key=lambda x: len(x['photos']),
                                           reverse=is_reverse)
                else:
                    sorted_albums = sorted(_albums,
                                           key=lambda x: x[sort_field],
                                           reverse=is_reverse)
                view = '_albums-list.html'
        else:
            sorted_albums = sorted(_albums,
                                   key=lambda x: len(x['photos']),
                                   reverse=True)
        unclassified = {
            "title": "Unclassified",
            "description": "Unclassified photos - not in any albums yet.",
            "amount_photos": 1
        }
        return render_template(view,
                               albums=sorted_albums,
                               unclassified=unclassified,
                               nb_photo_dict=nb_photos_dict,
                               api_svr=API_SVR)
    return None


@app.route('/albums', defaults={'path': None}, methods=('GET', 'POST'))
@app.route('/albums/', defaults={'path': None}, methods=('GET', 'POST'))
@app.route('/albums/<path>', methods=('GET', 'POST'))
def albums(path):
    if path is None:
        all_albums = db.albums.find()
        docs_as_extended_json = bson.json_util.dumps(all_albums)
        return docs_as_extended_json
    first_album = get_album(path)
    json_result = bson.json_util.dumps(first_album)
    return json_result


def get_album(path):
    album_doc = db.albums.find_one({"path": path})
    if album_doc is None:
        return None

    photo_ids = album_doc.get("photos", [])
    photos_details = []

    for photo_id in photo_ids:
        if photo_id is None or photo_id == "None":
            continue

        photo_doc = db.photos.find_one({"_id": photo_id})
        if photo_doc is None:
            app.logger.info("Photo object id %s was removed.", photo_id)
            continue

        photos_details.append(photo_doc)

    photos_details.reverse()

    album = {**album_doc}
    album["photos_details"] = photos_details
    return album


@app.route('/photo/save-photo-to-albums', methods=['GET', 'POST'])
@app.route('/photo/save-photo-to-albums/', methods=['POST'])
def save_photo_to_albums():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    photo_object_id = request_json['photo-object-id']
    photo_folder = request_json['photo-folder']
    photo_filename = request_json['photo-filename']
    newly_added_albums = request_json['newly-added-albums']
    updated_albums = []

    for album in newly_added_albums:
        if not photo_object_id:
            continue
        r = db.albums.find_one_and_update(
            {'path': album['path']},
            {
                '$addToSet': {'photos': ObjectId(photo_object_id)},
                '$set': {'date_modified': datetime.now(TZ_LONDON)},
            },
            return_document=ReturnDocument.AFTER
        )
        if r is not None and r.get('_id') is not None:
            updated_albums.append({
                "path": r['path'],
                "title": r['title']
            })

    result = {
        "updated-albums": updated_albums,
        "photo-object-id": photo_object_id,
        "photo-folder": photo_folder,
        "photo-filename": photo_filename
    }
    return Response(json.dumps(result), mimetype='application/json')


@app.route('/albums/add-photo', methods=['GET', 'POST'])
@app.route('/albums/add-photo/', methods=['POST'])
def albums_add_photo():
    all_albums = db.albums.find().sort([("date_modified", pymongo.DESCENDING)])
    # When the client clicks on Add to album button, it will render a select
    # box and a Save button
    return render_template('select_option_albums.html',
                           view=request.json['view'],
                           filename=request.json['photo-filename'],
                           albums=all_albums)


@app.route('/albums/remove-photos', methods=['GET', 'POST'])
@app.route('/albums/remove-photos/', methods=['POST'])
def albums_remove_photos():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    album_path = request_json['album-path']
    album = get_album(album_path)

    tobe_removed_photos = request_json['removed-photos']
    retval = do_album_remove_photos(album, tobe_removed_photos)

    return Response(json.dumps(retval), mimetype='application/json')


def do_album_remove_photos(album, tobe_removed_photos):
    retval = {}
    if (album is not None) and (album.get('photos') is not None):
        original_photos = album['photos']
        for photo in tobe_removed_photos:
            photo_oid = photo['photo-object-id']
            if ObjectId(photo_oid) in original_photos:
                original_photos.remove(ObjectId(photo_oid))

        r = db.albums.find_one_and_update(
            {'_id': album.get('_id')},
            {'$set': {
                "photos": original_photos,
                "date_modified": datetime.now(TZ_LONDON)
            }},
            return_document=ReturnDocument.AFTER
        )
        if r.get("_id") is not None:
            retval = {"path": r['path'], "title": r['title']}

    return retval


@app.route('/albums/delete', methods=('GET', 'POST'))
@app.route('/albums/delete/', methods=('GET', 'POST'))
def albums_delete():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    album_object_id = request_json['album-object-id']
    album_path = request_json['album-path']
    if album_path is not None and album_path is not None:
        query = {"_id": ObjectId(album_object_id)}
        result = db.albums.delete_one(query)
        app.logger.info(result)

    return jsonify(message="Deleted successfully")


@app.route('/albums/reorder-photos/', methods=('GET', 'POST'))
def albums_reorder_photos():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    album_object_id = request_json['album-object-id']
    array_photo_object_ids = request_json['photos']
    album = {
        "message": ("Updating the orders of the photos in the album "
                    + album_object_id)
    }
    cond = album_object_id != "" and len(array_photo_object_ids) > 0
    if cond:
        album = db.albums.update_one(
            {"_id": ObjectId(album_object_id)},
            {
                "$set": {
                    "photos": array_photo_object_ids,
                    "date_modified": datetime.now(TZ_LONDON)
                }
            }, upsert=False
        )
        app.logger.info(album)
        updated_album = db.albums.find_one({"_id": ObjectId(album_object_id)})
        if updated_album is not None and updated_album.get("_id") != "":
            album = {
                "message": ("Updated the orders of the photos in the album "
                            + album_object_id)
            }

    return json.dumps(album)


@app.route('/albums/update/', methods=['GET', 'POST'])
def albums_update():
    """
    Updates albums
    """
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    album_path = request_json['album-path']
    album_title = request_json['album-title']
    album_description = request_json['album-description']
    album = get_album(album_path)
    if album is not None:
        album = db.albums.update_one(
            {"_id": album.get('_id')},
            {
                "$set": {
                    "title": album_title,
                    "description": album_description,
                    "date_modified": datetime.now(TZ_LONDON)
                }
            }, upsert=False
        )
        app.logger.info(album)
    retval = {
        "message": "Updated completely",
        "title": album_title,
        "description": album_description
    }
    return Response(json.dumps(retval), mimetype='application/json')


@app.route('/albums/view/<string:path>', methods=['GET', 'POST'])
@do_cache(minutes=5, content_type='text/html;utf-8')
def albums_view(path):
    _albums = []
    for album in db.albums.find():
        _albums.append({
            "path": album['path'],
            "title": album['title'],
            "description": album['description']
        })

    if path == "unclassified":
        _photos = photo_unclassified()
        nb_photos = len(_photos)
        is_empty_album = nb_photos == 0
        ctx: dict = {
            "album_path": "unclassified",
            "album_title": "Unclassified",
            "status": "FOUND",
            "photos": _photos,
            "album_object_id": "unclassified",
            "albums": _albums,
            "nb_photos": nb_photos,
            "is_empty_album": is_empty_album,
            "has_more": False,
            "api_svr": API_SVR,
            "dict_album_values": {},
        }
        return render_template('album-view.html', **ctx)

    if path is None or path == '':
        return jsonify(message="Path is empty")

    album_doc = db.albums.find_one({"path": path})
    if album_doc is None:
        not_found_ctx: dict = {"status": "NOT_FOUND", "message": "No such album"}
        return render_template('album-view.html', **not_found_ctx)

    is_empty_album = not album_doc.get("photos")
    view = "album-view.html"

    if is_empty_album:
        return render_template(view, **{
            "status": "FOUND", "album": album_doc,
            "album_object_id": album_doc.get("_id"),
            "photos": [], "album_title": album_doc['title'],
            "albums": _albums, "album_path": path, "nb_photos": 0,
            "is_empty_album": True, "other_albums": None,
            "has_more": False, "api_svr": API_SVR,
            "dict_album_values": {},
        })

    sort = request.args.get('sort')

    if request.method == "POST":
        # Invoked when changing layout/view style — load all photos.
        request_json = request.get_json(silent=True)
        if not isinstance(request_json, dict):
            return jsonify({"error": "Invalid or missing JSON body"}), 400
        view = request_json['view']
        array_photos_object_ids = request_json['photos-object-ids']
        album = get_album(path)
        if album is None:
            return jsonify({"error": "Album not found"}), 404
        photos_details = album['photos_details']
        nb_photos = len(photos_details)
        bz = math.ceil(len(array_photos_object_ids) / 3)
        buckets = PhotoManager.create_buckets(photos_details, bz)
        return render_template(view, **{
            "status": "FOUND", "album": album,
            "album_path": album['path'],
            "album_title": album['title'],
            "albums": _albums,
            "photos": photos_details,
            "buckets": buckets, "nb_photos": nb_photos,
            "album_object_id": album.get("_id"),
            "is_empty_album": False,
            "has_more": False,
            "api_svr": API_SVR,
            "dict_album_values": {},
        })

    if sort is not None:
        # Sort or shuffle — load all photos so the full ordered set is shown.
        # _get_all_album_photos replaces get_album (N+1 queries → single $in)
        # and pushes field sorts to MongoDB instead of sorting in Python.
        if sort == "shuffle":
            photos_details, nb_photos = _get_all_album_photos(path, shuffle=True)
        else:
            s_opts = sort.split(";")
            sort_field = s_opts[0] if len(s_opts) > 0 else None
            sort_direction = s_opts[1] if len(s_opts) > 1 else 'down'
            photos_details, nb_photos = _get_all_album_photos(
                path, sort_field=sort_field, sort_dir=sort_direction
            )

        return render_template("_album_view_list.html", **{
            "status": "FOUND", "album": album_doc,
            "album_object_id": album_doc.get("_id"),
            "photos": photos_details,
            "album_title": album_doc['title'], "albums": _albums,
            "album_path": path, "nb_photos": nb_photos,
            "is_empty_album": nb_photos == 0,
            "other_albums": None, "has_more": False,
            "api_svr": API_SVR,
            "dict_album_values": {},
        })

    # Default GET: load only the first page; the client will fetch subsequent
    # pages via /api/v1/album/<path>/photos as the user scrolls.
    photos, nb_photos, has_more = _get_album_photos_page(path)
    return render_template("album-view.html", **{
        "status": "FOUND", "album": album_doc,
        "album_object_id": album_doc.get("_id"),
        "photos": photos, "album_title": album_doc['title'],
        "albums": _albums, "album_path": path,
        "nb_photos": nb_photos, "is_empty_album": False,
        "other_albums": None, "has_more": has_more,
        "api_svr": API_SVR,
        "dict_album_values": {},
    })


def photo_unclassified():
    _albums = db.albums.find()
    _albums = bson.json_util.dumps(_albums)
    _albums = bson.json_util.loads(_albums)

    _photos = db.photos.find()
    _photos = bson.json_util.dumps(_photos)
    _photos = bson.json_util.loads(_photos)

    _unclassified = []
    for photo in _photos:
        found = False
        for album in _albums:
            if str(photo.get("_id")) in album['photos']:
                found = True
                break
        if not found:
            _unclassified.append(photo)
    return _unclassified


@app.route('/photo/delete/', methods=['POST'])
@app.route('/photo/delete', methods=['POST'])
def photo_delete_via_post():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    photo_object_id = request_json['photo-object-id']
    query = {"_id": ObjectId(photo_object_id)}
    result = db.photos.delete_one(query)
    app.logger.debug(result)
    # delete the physical file
    photo_folder = request_json['photo-folder']
    photo_filename = request_json['photo-filename']
    abs_file_path = os.path.join(UPLOAD_FOLDER, photo_folder, photo_filename)
    pathlib.Path(str(abs_file_path)).unlink(missing_ok=True)
    # delete the photo object id where it is being associated with albums
    tobe_removed_photos = [
        {
            "photo-object-id": photo_object_id,
            "photo-folder": photo_folder,
            "photo-filename": photo_filename
        }
    ]
    for album in db.albums.find():
        do_album_remove_photos(album, tobe_removed_photos)

    return jsonify(message="Deleted successfully")


@app.route('/photo/delete/<string:object_id>', methods=('GET', 'POST'))
def photo_delete(object_id):
    if request.method == 'GET' and object_id is not None:
        print(f"deleting the photo object_id={object_id}")
        if len(object_id) != 24:
            return jsonify({"error": "photo id must be 24 characters long"})
        query = {"_id": ObjectId(object_id)}
        result = db.photos.delete_one(query)
        app.logger.debug(result)
        return jsonify({
            "deleted": True,
            "object_id": object_id,
            "size": len(object_id)
        })

    return jsonify({"error": "photo id does not exist"})


def _get_pagination_params():
    """
    Gets the pagination params
    """
    try:
        page = max(int(request.args.get("page", 1)), 1)
    except ValueError:
        page = 1
    PAGE_SIZE = 20
    skip = (page - 1) * PAGE_SIZE
    return skip, PAGE_SIZE


def _serialize_album(album):
    """
    Serialize the album to a dict
    Args:
        album (dict): album

    Returns:
        dict
    """
    if album is None:
        return {}

    return {
        "id": str(album.get("_id")),
        "title": album.get("title"),
        "description": album.get("description"),
        "path": album.get("path"),
    }


def _serialize_photo(doc):
    # Extract album info safely
    _albums = doc.get("belonged_to_albums", [])

    _photo = {
        "id": str(doc.get("_id", "")),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "courtesy": doc.get("courtesy", ""),
        "folder": doc.get("folder", ""),
        "filename": doc.get("filename", ""),
        "hash_md5": doc.get("hash_md5", ""),
        "date_uploaded": doc.get("date_uploaded"),
        "date_modified": doc.get("date_modified"),

        # New: Add the joined album data to the output
        "albums": [
            {
                "id": str(a.get("_id")),
                "title": a.get("title"),
                "path": a.get("path")
            } for a in _albums
        ]
    }
    return _photo


def _get_photos_page():
    """
    Gets the photos by parameters such as pagination, page size, and sort order.
    The photos are sanitised and converted to presentation forms.
    """
    skip, page_size = _get_pagination_params()

    cursor = (db.photos
              .find()
              .skip(skip)
              .sort([("date_uploaded", pymongo.DESCENDING)])
              .limit(page_size))
    return [_serialize_photo(doc) for doc in cursor]


def _get_latest_photos_with_albums(page=None):
    """
    Fetches one page of photos (newest-first) with their album memberships.
    If `page` is given, it overrides the `?page` query parameter so the
    initial page-render can always request page 1 regardless of the URL.
    """
    req_skip, page_size = _get_pagination_params()
    skip = (page - 1) * page_size if page is not None else req_skip

    pipeline = [
        {"$sort": {"date_uploaded": -1}},
        {"$skip": skip},
        {"$limit": page_size},
        {
            "$lookup": {
                "from": "albums",
                "localField": "_id",
                "foreignField": "photos",
                "as": "belonged_to_albums"
            }
        },
        {
            "$project": {
                "title": 1,
                "description": 1,
                "courtesy": 1,
                "folder": 1,
                "filename": 1,
                "date_uploaded": 1,
                "date_modified": 1,
                "belonged_to_albums.path": 1,
                "belonged_to_albums.title": 1,
                "belonged_to_albums._id": 1
            }
        }
    ]
    result = list(db.photos.aggregate(pipeline))
    return [_serialize_photo(doc) for doc in result]


def _get_album_photos_page(album_path, sort_field=None, sort_dir='down',
                           shuffle_seed=None):
    """
    Returns a paginated slice of photos for an album together with per-photo
    other-album cross-references.

    sort_field: 'title' | 'date_uploaded' | 'date_modified' | None
                  Sort is pushed to MongoDB; only the current page is fetched.
    sort_dir: 'down' (descending) or 'up' (ascending)
    shuffle_seed: integer seed for a deterministic shuffle.
                  The full ID list is shuffled with random.Random(seed), so
                  every page request with the same seed yields a consistent
                  order without any server-side state.

    Returns: (photo_docs, total_count, has_more)
    """
    skip, page_size = _get_pagination_params()

    album = db.albums.find_one({"path": album_path})
    if not album:
        return [], 0, False

    all_ids = list(reversed(album.get('photos', [])))
    valid_ids = [pid for pid in all_ids if str(pid) != 'None']
    total = len(valid_ids)

    if not valid_ids:
        return [], total, False

    has_more = (skip + page_size) < total

    if shuffle_seed is not None:
        # Shuffle only the ID list (cheap), then fetch just the current page.
        # Using a seeded RNG makes the order reproducible across pages without
        # storing any state on the server.
        shuffled = list(valid_ids)
        random.Random(shuffle_seed).shuffle(shuffled)
        paged_ids = shuffled[skip:skip + page_size]
        if not paged_ids:
            return [], total, False
        photo_details = _fetch_photos_ordered(paged_ids)

    elif sort_field in ('title', 'date_uploaded', 'date_modified'):
        # Push sort + pagination to MongoDB — never loads the full set into Python.
        mongo_dir = (pymongo.DESCENDING if sort_dir == 'down'
                     else pymongo.ASCENDING)
        cursor = (db.photos.find({"_id": {"$in": valid_ids}})
                  .sort(sort_field, mongo_dir)
                  .skip(skip)
                  .limit(page_size))
        photo_details: list[dict] = list(cursor)

    else:
        # Default: preserve the album's custom order.
        paged_ids = all_ids[skip:skip + page_size]
        if not paged_ids:
            return [], total, False
        paged_valid = [pid for pid in paged_ids if str(pid) != 'None']
        photo_details = _fetch_photos_ordered(paged_valid)

    fetched_ids = [p["_id"] for p in photo_details]
    other_albums_map = _build_other_albums_map(fetched_ids, album_path)
    for photo in photo_details:
        photo['other_albums'] = other_albums_map.get(str(photo.get("_id")), [])

    return photo_details, total, has_more


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    start_time = time.perf_counter()
    _photos = _get_latest_photos_with_albums()
    end_time = time.perf_counter()
    run_time = end_time - start_time
    app.logger.info("Executed in %.6f seconds to load 20 photos", run_time)

    tpl_name = 'photo-list.html'
    return render_template(template_name_or_list=tpl_name,
                           photos=_photos, api_svr=API_SVR)


@app.route('/photo/<path:path>', methods=['GET', 'POST'])
def photo_read(path):
    try:
        return send_from_directory(UPLOAD_FOLDER, path,
                                   as_attachment=True, max_age=86400)
    except FileNotFoundError as exception:
        app.logger.error("404: File Not Found %s", exception)
        return None


@app.route('/api/v1/photo/update', methods=['PATCH'])
def update_photo():
    request_json = request.get_json()
    photo_object_id = request_json['photo-id']
    photo_title = request_json['new-photo-title']
    app.logger.info("Updating photo %s with title %s", photo_object_id, photo_title)
    if photo_title is None or photo_title == "" or photo_object_id is None:
        app.logger.error("Invalid photo title or photo id. Cannot update!")
        return jsonify({"error": "Cannot update the photo title or photo id "
                                 "empty"}), 400
    result = db.photos.update_one(
        {"_id": ObjectId(photo_object_id)},
        {
            "$set": {
                "title": photo_title,
                "date_modified": datetime.now(TZ_LONDON)
            }
        }, upsert=False
    )
    if result.modified_count == 0:
        return jsonify(
            {
                "error": "Cannot update the photo title or photo id "
            }), 400
    # TODO: check the update failed or not
    return jsonify(message="photo updated"), 200


@app.route('/photo/update', methods=('GET', 'POST'))
def photo_update():
    request_json = request.get_json(silent=True)
    if not isinstance(request_json, dict):
        return jsonify({"error": "Invalid or missing JSON body"}), 400
    photo_object_id = request_json['photo-object-id']
    photo_title = request_json['photo-title']
    photo_description = request_json['photo-description']
    photo_courtesy = request_json['photo-courtesy']
    app.logger.info("Photo requesting to be updated: %s", request_json)
    result = db.photos.update_one(
        {"_id": ObjectId(photo_object_id)},
        {
            "$set": {
                "title": photo_title,
                "description": photo_description,
                "courtesy": photo_courtesy,
                "date_modified": datetime.now(TZ_LONDON)
            }
        }, upsert=False
    )
    app.logger.info("Updated result: %s", result)
    retval = {"message": "Updated completely", "title": photo_title}
    return Response(json.dumps(retval), mimetype='application/json')


@app.route('/photo/upload', methods=['GET', 'POST'])
def photo_upload():
    """
    Upload photos via Form, Postman or Curl
    """
    if request.method == 'POST':
        if 'file' in request.files:
            app.logger.info("Upload the photo via browsing it via form")
        else:
            app.logger.info("Upload the photo via postman, terminal or post")
        result = do_upload_photo(request)
        result = result.json if isinstance(result, Response) else result

        app.logger.debug(result)
        return result
    return render_template("photo-upload.html")


@app.route('/photo/show/<string:unique_key>', methods=['GET'])
def photo_show(unique_key):
    """
    Shows a photo by hash_md5 or string of the object id
    """
    # 0. Check the input and return
    if unique_key is None:
        return render_template("photo-upload.html")

    # 1. Determine if search_value is a valid ObjectId string or an MD5 hash
    match_condition = {}
    if ObjectId.is_valid(unique_key):
        # It's an ID
        match_condition = {"_id": ObjectId(unique_key)}
    elif len(unique_key) == 32:
        # It's an MD5 hash
        match_condition = {"hash_md5": unique_key}

    # 2. Prepare the pipeline
    pipeline = [
        # Stage 1: Find the photo
        {"$match": match_condition},

        # Stage 2: Reverse Lookup into Albums
        {
            "$lookup": {
                "from": "albums",
                "localField": "_id",
                "foreignField": "photos",  # The field in albums containing photo IDs
                "as": "member_of_albums"
            }
        },

        # Stage 3: Projection (Clean up the output)
        {
            "$project": {
                # Add all these fields so they aren't deleted!
                "title": 1,
                "description": 1,
                "courtesy": 1,
                "folder": 1,
                "filename": 1,
                "hash_md5": 1,
                "date_uploaded": 1,
                "date_modified": 1,

                # Keep the album info
                "member_of_albums._id": 1,
                "member_of_albums.path": 1,
                "member_of_albums.title": 1,
                "member_of_albums.description": 1
            }
        }
    ]

    _photos = list(db.photos.aggregate(pipeline))
    if _photos is not None:
        all_albums = list(db.albums.find({}, {"path": 1, "title": 1}))
        return render_template("photo-show.html",
                               photos=_photos,
                               albums=all_albums,
                               dict_album_values={})
    return None


@app.route('/photo/view', methods=['GET', 'POST'])
def photo_view():
    photos = _get_latest_photos_with_albums(page=1)
    _, page_size = _get_pagination_params()
    has_more = len(photos) >= page_size
    all_albums = list(db.albums.find({}, {"path": 1, "title": 1}))
    return render_template('photo-view.html',
                           photos=photos, has_more=has_more,
                           albums=all_albums, dict_album_values={},
                           api_svr=API_SVR)


def do_download_image(storage_location, image_url, out_filename=None):
    # this function is working like a charm for Facebook images
    if not image_url or image_url is None:
        return jsonify(message="Image URL not found!")
    res = requests.get(image_url, stream=True, timeout=30)
    # Request the image and save it:
    if out_filename is None:
        out_filename = str(uuid.uuid4()) + ".jpg"
    with open(storage_location + "/" + out_filename, "wb") as f:
        f.write(res.content)
        hash_md5 = hashlib.md5(res.content).hexdigest()

    return {"filename": out_filename, "hash_md5": hash_md5}


def do_upload_photo(req):
    """
    Handle the uploading of photos
    """
    metadata_string = req.form.get('metadata')
    if not metadata_string:
        return jsonify({'message': 'Missing metadata field in form data'}), 400
    try:
        # Use Python's built-in JSON library to convert the string back to
        # a dictionary
        metadata = json.loads(metadata_string)
        title = metadata.get('title', 'Untitled')
        photo_url = metadata.get('photo-url', 'N/A')
        description = metadata.get('description', 'N/A')
        courtesy = metadata.get('courtesy', 'Unknown')

    except json.JSONDecodeError:
        return jsonify({'message': 'Invalid JSON format in the metadata'}), 400

    submission_folder = req.headers["Submission-Folder"] \
        if ("Submission-Folder" in req.headers
            and req.headers["Submission-Folder"] is not None) \
        else infer_submission_folder()
    UPLOAD_DIR = os.path.join(app.config['UPLOAD_FOLDER'], submission_folder)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    # regenerate a new file for both cases
    filename = str(uuid.uuid4()) + ".jpg"
    if 'file' in req.files:
        file = req.files['file']
        app.logger.info("Uploading a local photo...")
        # filename = secure_filename(file.filename)
        # filename = file.filename
        abs_file_path = os.path.join(str(UPLOAD_DIR), filename)
        file.save(abs_file_path)
        with open(abs_file_path, "rb") as f:
            hash_md5 = hashlib.md5(f.read()).hexdigest()
    else:
        # download the image from the provided image URL
        app.logger.info("Downloading a photo from a remote location...")
        if photo_url is not None:
            pass
        elif ("Image-URL" in req.headers
                and req.headers["Image-URL"] is not None):
            photo_url = req.headers["Image-URL"]
        elif "photo-url" in req.json:
            photo_url = req.json["photo-url"]
        else:
            photo_url = req.form['photo-url']
        if photo_url is None or photo_url == '':
            app.logger.error("Image URL not found!")
            return render_template('photo-list.html',
                                   **{"message": "Image URL not found!"})
        global nb_downloads
        try:
            result = do_download_image(UPLOAD_DIR, photo_url, filename)
            nb_downloads += 1
        except requests.exceptions.HTTPError as e:
            app.logger.error("HTTP error occurred: %s", e)
            return jsonify({'message': str(e)}), 500
        except requests.exceptions.ConnectionError as e:
            app.logger.error("Connection error occurred: %s", e)
            return jsonify({'message': str(e)}), 500
        except requests.exceptions.RequestException as e:
            app.logger.error("A general error occurred: %s", e)
            return jsonify({'message': str(e)}), 500
        finally:
            app.logger.info("The number of downloads the remote photo: %s", nb_downloads)

        if isinstance(result, Response):
            return result
        filename = result["filename"]
        hash_md5 = result["hash_md5"]

    # find any existing photos with hash_md5
    col_photos = db.photos
    docs = col_photos.find_one({"hash_md5": hash_md5})
    if docs is not None:
        pp = pprint.PrettyPrinter(indent=4)
        pp.pprint(docs)
        app.logger.debug(docs)
        col_albums = []
        all_albums = db.albums.find()
        for album in all_albums:
            _photos = album['photos']
            if docs["_id"] in _photos:
                col_albums.append(album['path'])
        msg = ("Photo exists in DB! The photo can be found in the albums: "
               ",".join(col_albums))
        app.logger.debug(msg)
        # move or delete the photo to another folder
        abs_file_path = os.path.join(str(UPLOAD_DIR), filename)
        # https://stackoverflow.com/a/59185523/865603
        pathlib.Path(abs_file_path).unlink(missing_ok=True)
        # TODO: figure out how to use the returned json below on the view
        message = filename + ' exists!'
        return jsonify(message=message,
                       submission_folder=submission_folder,
                       object_id=str(docs["_id"]),
                       filename=docs["filename"],
                       exist_in_albums=",".join(col_albums))
    message = f"{filename} is a new photo."
    app.logger.info(message)

    # save the file's metadata into MongoDB
    save_metadata(submission_folder, filename, title, description, courtesy,
                  hash_md5)
    return {
        'message': message,
        'submission_folder': submission_folder,
        'filename': filename, 'title': title,
        'description': description, 'origin': courtesy,
        'hash_md5': hash_md5
    }


@app.route('/file/upload', methods=['GET', 'POST'])
def file_upload():
    file = request.files['file']
    # file.read() is the same as file.stream.read()
    img_key = hashlib.md5(file.read()).hexdigest()
    print(img_key)


def dict_photos_albums(list_photos, album_path):
    _albums = db.albums.find()
    _albums = bson.json_util.dumps(_albums)
    _albums = bson.json_util.loads(_albums)
    other_albums_dict = {}
    for photo in list_photos:
        photo_id = str(photo.get("_id"))
        for album in _albums:
            if photo_id in album['photos'] and album['path'] != album_path:
                if photo_id in other_albums_dict:
                    other_albums_dict[photo_id].append({
                        "path": album['path'], "title": album['title']
                    })
                else:
                    other_albums_dict[photo_id] = [{
                        "path": album['path'], "title": album['title']
                    }]
    return other_albums_dict


def _fetch_photos_ordered(ids) -> list[dict]:
    """Fetch photo docs for the given ObjectId list and return them in id order."""
    raw: list[dict] = list(db.photos.find({"_id": {"$in": ids}}))
    by_id = {str(p["_id"]): p for p in raw}
    return [by_id[str(pid)] for pid in ids if str(pid) in by_id]


def _build_other_albums_map(photo_object_ids, current_album_path):
    """
    Returns {photo_id_str: [{path, title}, ...]} for every album (other than
    the current one) that contains at least one of the supplied photo IDs.

    Uses a single $in a query instead of iterating over all albums in Python
    and avoids the bson.json_util serialisation round-trip of dict_photos_albums.
    """
    other_albums = list(db.albums.find(
        {"path": {"$ne": current_album_path}, "photos": {"$in": photo_object_ids}},
        {"path": 1, "title": 1, "photos": 1}
    ))
    photo_id_set = {str(pid) for pid in photo_object_ids}
    result = {}
    for album in other_albums:
        for pid in album.get('photos', []):
            pid_str = str(pid)
            if pid_str in photo_id_set:
                result.setdefault(pid_str, []).append(
                    {"path": album['path'], "title": album['title']}
                )
    return result


def _get_all_album_photos(album_path, sort_field=None, sort_dir='down',
                          shuffle=False):
    """
    Fetches every photo in an album using a single $in a query (replacing the
    N+1 find_one loop in get_album). Used by the sort/shuffle path which must
    show the complete set.

    - sort_field: 'title' | 'date_uploaded' | 'date_modified' | None
      When supplied, the sort is pushed to MongoDB rather than done in Python.
    - sort_dir: 'down' (descending) or 'up' (ascending)
    - shuffle:   randomise order after fetching (overrides sort_field)

    Returns (photo_docs, total_count). Each doc is a raw MongoDB document with
    an 'other_albums' list attached.
    """
    album = db.albums.find_one({"path": album_path})
    if not album:
        return [], 0

    all_ids = list(reversed(album.get('photos', [])))
    valid_ids = [pid for pid in all_ids if str(pid) != 'None']
    if not valid_ids:
        return [], 0

    if not shuffle and sort_field in ('title', 'date_uploaded', 'date_modified'):
        mongo_dir = (pymongo.DESCENDING if sort_dir == 'down'
                     else pymongo.ASCENDING)
        photos: list[dict] = list(
            db.photos.find({"_id": {"$in": valid_ids}})
            .sort(sort_field, mongo_dir)
        )
    else:
        raw: list[dict] = list(db.photos.find({"_id": {"$in": valid_ids}}))
        if shuffle:
            random.shuffle(raw)
            photos = raw
        else:
            by_id = {str(p["_id"]): p for p in raw}
            photos = [by_id[str(pid)] for pid in valid_ids if str(pid) in by_id]

    other_albums_map = _build_other_albums_map(valid_ids, album_path)
    for photo in photos:
        photo['other_albums'] = other_albums_map.get(str(photo.get("_id")), [])

    return photos, len(photos)


@app.route('/api/v1/photos', methods=['GET'])
def get_photos():
    """
    Returns one page of photos as JSON + pre-rendered HTML for infinite scroll.
    """
    page = request.args.get('page', 1, type=int)
    app.logger.info("Loading page %s...", page)
    _photos = _get_latest_photos_with_albums()
    _, page_size = _get_pagination_params()
    has_more = len(_photos) >= page_size
    content = render_template(template_name_or_list="_photo-list.html",
                              photos=_photos)
    return jsonify(photos=_photos, content=content, has_more=has_more)


@app.route('/api/v1/album/<string:path>/photos', methods=['GET'])
def get_album_photos(path):
    """
    Returns one paginated page of photos for an album as JSON + pre-rendered
    HTML, for use by the album-view infinite scroll and sorted views.

    Optional query params:
      sort=<field>;<dir> e.g. sort=title;down (field sort, paginated)
      page=<n> page number (default 1)
    """
    sort_field, sort_dir = None, 'down'
    sort_param = request.args.get('sort', '')
    if sort_param:
        parts = sort_param.split(';')
        sf = parts[0]
        if sf in ('title', 'date_uploaded', 'date_modified'):
            sort_field = sf
        sort_dir = parts[1] if len(parts) > 1 else 'down'

    shuffle_seed = request.args.get('shuffle', None, type=int)

    photos, _, has_more = _get_album_photos_page(
        path, sort_field=sort_field, sort_dir=sort_dir, shuffle_seed=shuffle_seed
    )
    content = render_template(
        "_album_view_photo_rows.html",
        **{"photos": photos, "album_path": path, "status": "FOUND"},
    )
    return jsonify(content=content, has_more=has_more, count=len(photos))


@app.route('/api/v1/album/<string:path>/slideshow', methods=['GET'])
def get_album_slideshow(path):
    """
    Returns all photo URLs and titles for an album — used by the slideshow player.
    Only fetches folder/filename/title, so it is lightweight even for large albums.
    """
    album = db.albums.find_one({"path": path})
    if not album:
        return jsonify(photos=[])
    all_ids = list(reversed(album.get('photos', [])))
    valid_ids = [pid for pid in all_ids if str(pid) != 'None']
    raw = list(db.photos.find(
        {"_id": {"$in": valid_ids}},
        {"folder": 1, "filename": 1, "title": 1}
    ))
    by_id = {str(p["_id"]): p for p in raw}
    photos = []
    for pid in valid_ids:
        p = by_id.get(str(pid))
        if p is not None:
            photos.append({
                "url": f"/photo/{p['folder']}/{p['filename']}",
                "title": p.get("title", "")
            })
    return jsonify(photos=photos)


@app.route('/api/v1/photos/gallery', methods=['GET'])
def get_gallery_photos():
    """
    Returns one page of photos as JSON + pre-rendered HTML for the gallery infinite scroll.
    """
    photos = _get_latest_photos_with_albums()
    _, page_size = _get_pagination_params()
    has_more = len(photos) >= page_size
    content = render_template('_photo-view-items.html', photos=photos)
    return jsonify(content=content, has_more=has_more, count=len(photos))


def get_album_with_photo_cross_references(album_id_str):
    pipeline = [
        # 1. Start with the specific Album
        {"$match": {"_id": ObjectId(album_id_str)}},

        # 2. Join with the Photos collection to get full photo data
        {
            "$lookup": {
                "from": "photos",
                "localField": "photos",   # The array of photo IDs in the album
                "foreignField": "_id",
                "as": "photo_list"
            }
        },

        # 3. "Flatten" the photo_list so we can look up on individual photos
        {"$unwind": "$photo_list"},

        # 4. For each photo, find ALL albums that contain its ID
        {
            "$lookup": {
                "from": "albums",
                "localField": "photo_list._id",
                "foreignField": "photos",
                "as": "photo_list.all_albums"
            }
        },

        # 5. Group the photos back into an array for the original album
        {
            "$group": {
                "_id": "$_id",
                "title": {"$first": "$title"},
                "photos": {"$push": "$photo_list"}
            }
        },

        # 6. Clean up: Project only the necessary fields for the sibling albums
        {
            "$project": {
                "title": 1,
                "photos._id": 1,
                # "photos.url": 1,
                "photos.title": 1,
                "photos.description": 1,
                "photos.courtesy": 1,
                "photos.folder": 1,
                "photos.filename": 1,
                "photos.hash_md5": 1,
                "photos.date_uploaded": 1,
                "photos.date_modified": 1,
                "photos.all_albums._id": 1,
                "photos.all_albums.title": 1,
                "photos.all_albums.description": 1,
                "photos.all_albums.path": 1,
            }
        }
    ]

    results = list(db.albums.aggregate(pipeline))
    result = dict({})
    if results[0] is not None:
        result["_id"] = str(results[0]["_id"])
        result["title"] = results[0]["title"]
        result["photos"] = []
        for _photo in results[0]["photos"]:
            serialized = _serialize_photo(_photo)
            serialized["albums"] = [_serialize_album(a) for a in _photo[
                "all_albums"]]
            result["photos"].append(serialized)
    return result


@app.route('/api/v1/album/<string:object_id>', methods=['GET'])
def get_album_by_id(object_id):
    _photos = get_album_with_photo_cross_references(object_id)
    return jsonify(photos=_photos)


if __name__ != "__main__":
    # 1. Locate Gunicorn's error logger
    gunicorn_logger = logging.getLogger('gunicorn.error')

    # 2. Set Flask's logger handlers to match Gunicorn's
    app.logger.handlers = gunicorn_logger.handlers

    # 3. Match the log levels (so INFO or DEBUG messages actually show up)
    app.logger.setLevel(gunicorn_logger.level)

    # 4. (Optional) Propagate messages to the root logger
    # This ensures third-party library logs also go to Gunicorn
    logging.getLogger().handlers = gunicorn_logger.handlers
