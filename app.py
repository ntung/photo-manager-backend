import hashlib
import json
import math
import os
import pathlib
import pprint
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
from utils import PhotoManager

load_dotenv() # loads variables from .env into environment

TMP_BM = tempfile.gettempdir() + "/photo-manager/upload"
os.makedirs(TMP_BM, exist_ok=True)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', TMP_BM)

client = MongoClient('localhost', 27017)
db = client.photodb
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
    app.logger.info("current submission folder: {}".format(location))
    return location


# https://www.linkedin.com/advice/0/what-some-best-practices-managing-flask-session-expiration
# https://www.maskaravivek.com/post/how-to-add-http-cachecontrol-headers-in-flask/
# https://stackoverflow.com/questions/704561/ns-binding-aborted-shown-in-firefox-with-httpfox
def do_cache(minutes=5, content_type='application/json; charset=utf-8'):
    """ Flask decorator that allow to set Expire and Cache headers. """

    def fwrap(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            r = f(*args, **kwargs)
            then = datetime.now() + timedelta(minutes=minutes)
            rsp = Response(r, content_type=content_type)
            v = then.strftime("%a, %d %b %Y %H:%M:%S GMT")
            rsp.headers.add('Expires', v)
            v = 'public,max-age=%d' % int(60 * minutes)
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
    _albums = request_json['albums']
    _photos = request_json['photos']
    for photo_id in _photos:
        for album in _albums:
            album_doc = db.albums.find_one({'path': album['path']})
            if album_doc:
                photo_set = album_doc['photos']
                if photo_set is None:
                    photo_set = [photo_id]
                elif photo_id not in photo_set:
                    photo_set.append(photo_id)
                if photo_set:
                    db.albums.update_one(
                        {
                            "_id": ObjectId(album_doc.get("_id"))
                        },
                        {
                            "$set":
                            {
                                'photos': photo_set,
                                'date_modified': datetime.now(TZ_LONDON)
                            }
                        }, upsert=False)

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
        app.logger.info("{}\t{}".format(title, description))

        if not title:
            # stop creating untitled album
            return redirect(url_for('photo_albums'))

        path = slugify(title)
        r = db.albums.insert_one({
            'path': path, 'title': title, 'description': description,
            'photos': [],
            'date_created': datetime.now(TZ_LONDON),
            'date_modified': datetime.now(TZ_LONDON)
        })
        app.logger.info("Inserted a new record to db.photos {}".format(r))
        return redirect(url_for('photo_albums'))
    elif request.method == 'GET':
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
                is_reverse = not (sort_direction == "down")
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
        # bson.json_util.loads(docs_as_extended_json)
        return docs_as_extended_json
    else:
        first_album = get_album(path)
        json_result = bson.json_util.dumps(first_album)
        return json_result


def get_album(path):
    first_album = db.albums.find_one({"path": path})
    if first_album is None:
        return None

    photos_in_album = first_album['photos']
    photo_details = []
    for photo_id in photos_in_album:
        if photo_id == 'None':
            continue
        photo_doc = db.photos.find_one({"_id": photo_id})
        if photo_doc is not None:
            photo_details.append(photo_doc)
        else:
            app.logger.info("Photo object id {} was removed.".format(photo_id))

    # Sort the list of photos by the date uploaded
    # sorted_photo_details = sorted(photos_details,
    # key=lambda x: x['date_uploaded'], reverse=True)
    # reverse the list of photos to make sure that
    # we display photos of an album in the chronological order
    photo_details.reverse()
    # After implementing the feature: reordering photos,
    # we want to keep the order we have done on UX/UI
    # Therefore, we need to stop reversing the array of photos.
    first_album["photos_details"] = photo_details  # sorted_photo_details

    return first_album


@app.route('/photo/save-photo-to-albums', methods=['GET', 'POST'])
@app.route('/photo/save-photo-to-albums/', methods=['POST'])
def save_photo_to_albums():
    request_json = request.get_json(silent=True)
    photo_object_id = request_json['photo-object-id']
    photo_folder = request_json['photo-folder']
    photo_filename = request_json['photo-filename']
    newly_added_albums = request_json['newly-added-albums']
    updated_albums = []

    for album in newly_added_albums:
        album = get_album(album['path'])
        if album is not None:
            updated_photo_list = album["photos"]
            if ((photo_object_id != "") and
                    (ObjectId(photo_object_id) not in updated_photo_list)):
                updated_photo_list.append(ObjectId(photo_object_id))

            r = db.albums.find_one_and_update(
                {'_id': album.get('_id')},
                {
                    '$set': {
                        "photos": updated_photo_list,
                        "date_modified": datetime.now(TZ_LONDON)}
                }, return_document=ReturnDocument.AFTER
            )
            if r.get('_id') is not None:
                updated_albums.append({
                    "path": album['path'],
                    "title": album['title']
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
    # When the client clicks on Add to album button, is will render a select
    # box and a Save button
    return render_template('select_option_albums.html',
                           view=request.json['view'],
                           filename=request.json['photo-filename'],
                           albums=all_albums)


@app.route('/albums/remove-photos', methods=['GET', 'POST'])
@app.route('/albums/remove-photos/', methods=['POST'])
def albums_remove_photos():
    request_json = request.get_json(silent=True)
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
    album_object_id = request_json['album-object-id']
    array_photo_object_ids = request_json['photos']
    album = {
        "message": ("Updating the orders of the photos in the album " +
                    album_object_id)
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
        if updated_album.get("_id") != "":
            album = {
                "message": ("Updated the orders of the photos in the album "
                            + album_object_id)
            }

    return json.dumps(album)


@app.route('/albums/update/', methods=('GET', 'POST'))
def albums_update():
    request_json = request.get_json(silent=True)
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


@app.route('/albums/view/<path>', methods=('GET', 'POST'))
@do_cache(minutes=5, content_type='text/html;utf-8')
def albums_view(path):
    _albums = []
    for album in db.albums.find():
        _albums.append({
            "path": album,
            "title": album['title'],
            "description": album['description']
        })

    if path == "unclassified":
        _photos = photo_unclassified()
        nb_photos = len(_photos)
        is_empty_album = nb_photos == 0
        return render_template('album-view.html',
                               album_path='unclassified',
                               album_title='Unclassified',
                               status="FOUND",
                               photos=_photos,
                               album_object_id="unclassified",
                               albums=_albums,
                               nb_photos=nb_photos,
                               is_empty_album=is_empty_album,
                               api_svr=API_SVR)
    status = "FOUND"
    tt = None
    if path is None or path == '':
        return jsonify(message="Path is empty")
    else:
        album = get_album(path)
        if album is None:
            status = "NOT_FOUND"
            return render_template('album-view.html',
                                   status=status, message="No such album")
        is_empty_album = not album["photos"]
        view = "album-view.html"
        nb_photos = 0
        if not is_empty_album:
            status = "FOUND"
            nb_photos = len(album["photos_details"])

            if request.method == "POST":
                # it is invoked when changing layout/view style
                request_json = request.get_json(silent=True)
                view = request_json['view']
                array_photos_object_ids = request_json['photos-object-ids']
                photos_details = album['photos_details']
                bz = math.ceil(len(array_photos_object_ids) / 3)
                buckets = PhotoManager.create_buckets(photos_details, bz)
                # TODO: using array_photos_object_ids to get the same orders
                #  of photos on the current page
                # current_ordered_photos = []
                # for id in array_photos_object_ids:

                return render_template(view, status=status, album=album,
                                       album_path=album['path'],
                                       album_title=album['title'],
                                       albums=_albums,
                                       photos=album['photos_details'],
                                       buckets=buckets, nb_photos=nb_photos,
                                       album_object_id=album.get("_id"),
                                       is_empty_album=is_empty_album,
                                       api_svr=API_SVR)

            sort = request.args.get('sort')
            if sort is not None and sort == "shuffle":
                import random
                view = "_album_view_list.html"
                random.shuffle(album["photos_details"])
            elif sort is not None:
                app.logger.info(sort)

                s_opts = sort.split(";")
                sort_field = s_opts[0]
                sort_direction = s_opts[1]
                photos_details = album["photos_details"]
                if sort_field in ["title", "date_uploaded", "date_modified"]:
                    is_reverse = sort_direction == "down"
                    sorted_photos_details = sorted(photos_details,
                                                   key=lambda x: x[sort_field],
                                                   reverse=is_reverse)
                    album["photos_details"] = sorted_photos_details

                view = "_album_view_list.html"
            tt = dict_photos_albums(album["photos_details"], album["path"])
            for photo in album["photos_details"]:
                photo_id = str(photo.get("_id"))
                if photo_id in tt:
                    photo['other_albums'] = tt[photo_id]

        return render_template(view, status=status, album=album,
                               album_object_id=album.get("_id"),
                               photos=album['photos_details'],
                               album_title=album['title'], albums=_albums,
                               album_path=album['path'], nb_photos=nb_photos,
                               is_empty_album=is_empty_album,
                               other_albums=tt, api_svr=API_SVR)


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
        page = int(request.args.get("page", 1))
        if page < 1:
            page = 1
    except ValueError:
        page = 1
    PAGE_SIZE = 20
    skip = (page - 1) * PAGE_SIZE
    return skip, PAGE_SIZE


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


def _get_latest_photos_with_albums():
    # Calculate how many documents to skip
    # Page 1 skips 0, Page 2 skips 20, etc.
    skip, page_size = _get_pagination_params()

    pipeline = [
        { "$sort": { "date_uploaded": -1 } },
        { "$skip": skip },  # Skip the previous pages
        { "$limit": page_size },   # Limit to current page size
        {
            "$lookup": {
                "from": "albums",
                "localField": "_id",      # The ID of the photo
                "foreignField": "photos", # containing the photo IDs
                "as": "belonged_to_albums"
            }
        },
        {
            "$project": {
                # Add all these fields so they aren't deleted!
                "title": 1,
                "description": 1,
                "courtesy": 1,
                "folder": 1,
                "filename": 1,
                "date_uploaded": 1,
                "date_modified": 1,

                # Keep your album info
                "belonged_to_albums.path": 1,
                "belonged_to_albums.title": 1,
                "belonged_to_albums._id": 1
            }
        }
    ]
    result  = list(db.photos.aggregate(pipeline))
    _photos = [_serialize_photo(doc) for doc in result]
    return _photos


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    start_time = time.perf_counter()
    _photos = _get_latest_photos_with_albums()
    end_time = time.perf_counter()
    run_time = end_time - start_time
    app.logger.info(f"Executed in {run_time:.6f} seconds to load 20 photos")

    tpl_name = 'photo-list.html'
    return render_template(template_name_or_list=tpl_name,
                           photos=_photos, api_svr=API_SVR)


@app.route('/photo/<path:path>', methods=['GET', 'POST'])
def photo_read(path):
    try:
        return send_from_directory(UPLOAD_FOLDER, path,
                                   as_attachment=True, max_age=86400)
    except FileNotFoundError as exception:
        app.logger.error("404: File Not Found " + str(exception))
        return None


@app.route('/api/v1/photo/update', methods=['PATCH'])
def update_photo():
    request_json = request.get_json()
    photo_object_id = request_json['photo-id']
    photo_title = request_json['new-photo-title']
    app.logger.info(f"Updating photo {photo_object_id} with title"
                    f" {photo_title}")
    if photo_title is None or photo_title == "" or photo_object_id is None:
        app.logger.error("Invalid photo title or photo id. Cannot update!")
        return jsonify({"error": "Cannot update the photo title or photo id "
                                 "empty"}), 200
    result = db.photos.update_one(
        {"_id": ObjectId(photo_object_id)},
        {
            "$set": {
                "title": photo_title,
                "date_modified": datetime.now(TZ_LONDON)
            }
        }, upsert=False
    )
    # TODO: check the update failed or not
    return jsonify(message="photo updated"), 200


@app.route('/photo/update', methods=('GET', 'POST'))
def photo_update():
    request_json = request.get_json(silent=True)
    photo_object_id = request_json['photo-object-id']
    photo_title = request_json['photo-title']
    photo_description = request_json['photo-description']
    photo_courtesy = request_json['photo-courtesy']
    app.logger.info("Photo requesting to be updated: {}".format(request_json))
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
    app.logger.info("Updated result: {}".format(result))
    retval = {"message": "Updated completely", "title": photo_title}
    return Response(json.dumps(retval), mimetype='application/json')


@app.route('/photo/upload', methods=('GET', 'POST'))
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
    else:
        return render_template("photo-upload.html")


@app.route('/photo/show/<string:unique_key>', methods=['GET'])
def photo_show(unique_key):
    """
    Shows a photo by hash_md5 or string of the object id
    """
    if unique_key is None:
        return render_template("photo-upload.html")
    docs = None
    if len(unique_key) == 32:
        # hash_md5
        docs = db.photos.find({"hash_md5": unique_key})
    elif len(unique_key) == 24:
        # string of the object id
        docs = db.photos.find({"_id": ObjectId(unique_key)})
    if docs is not None:
        return render_template("photo-show.html",
                               photos=docs)
    return None


@app.route('/photo/view', methods=['GET', 'POST'])
def photo_view():
    all_photos = db.photos.find().sort([("date_uploaded", pymongo.DESCENDING)])
    # divide 4 because I installed this layout [1]
    # [1] https://www.w3schools.com/howto/howto_js_image_grid.asp
    bucket_size = math.ceil(db.photos.count_documents({}) / 4)
    buckets = PhotoManager.create_buckets(all_photos, bucket_size)

    # after looping over all_photos as a Cursor, all_photos is empty
    all_photos = PhotoManager.flatten_concatenation(buckets)

    return render_template('photo-view.html',
                           photos=all_photos, buckets=buckets, api_svr=API_SVR)


def do_download_image(storage_location, image_url, out_filename=None):
    # this function is working like a charm for Facebook images
    if not image_url or image_url is None:
        return jsonify(message="Image URL not found!")
    res = requests.get(image_url, stream=True)
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
        # file.filename and file.filename is not None:
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
                                   message="Image URL not found!")
        result = do_download_image(UPLOAD_DIR, photo_url, filename)
        app.logger.debug(f"Download completed! {result}")
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
            if str(docs["_id"]) in _photos:
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
                       filename=docs["filename"],
                       exist_in_albums=",".join(col_albums))
    else:
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
    other_albums_dict = dict()
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


@app.route('/api/v1/photos', methods=['GET'])
def get_photos():
    """
    Gets the photos by parameters such as pagination, page size, and sort order.
    The photos are sanitised and converted to presentation forms.
    """
    page = request.args.get('page', 1, type=int)
    app.logger.info(f"Loading page {page}...")
    _photos = _get_latest_photos_with_albums()
    content = render_template(template_name_or_list="_photo-list.html",
                              photos=_photos,)
    return jsonify(photos=_photos, content=content)


if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5500, debug=True, threaded=False,
    # ssl_context='adhoc')
    app.run(host='0.0.0.0', port=5500, debug=True, threaded=False,
            ssl_context=('cert.pem', 'key.pem'))
