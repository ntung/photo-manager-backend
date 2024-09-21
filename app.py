import hashlib
import json
import math
import os
import pathlib
import tempfile
import uuid
from datetime import datetime
from logging.config import dictConfig

import bson
import bson.json_util
import pymongo
import pytz
import requests
from bson import ObjectId
from flask import Flask, Response
from flask import jsonify, render_template, request, url_for, redirect, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from slugify import slugify

from utils import PhotoManager
from utils import PhotoManager

TMP_BM = tempfile.gettempdir() + "/photo-manager/upload"
os.makedirs(TMP_BM, exist_ok=True)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', TMP_BM)

client = MongoClient('localhost', 27017)
db = client.flask_db
todos = db.todos

TZ_LONDON = pytz.timezone("Europe/London")

"""
TODO LIST
        0/ Calculate aaaa, aaab, aaac... submission folders
Done    1/ Delete photos and albums: will delete physical photos and albums too.
Progress2/ Add/edit,remove photos to/out albums
        3/ Improve the views by allowing zoom, click open a single photo
Progress4/ Improve adding photos: add tags, hashtags, keywords, etc.
        5/ Loading more data when scrolling or pagination, do not load all once.
Done    6/ View photos by albums
Done    7/ Add/Edit an album: edit title, description; add more photos...
Done    8/ Check md5 to avoid repeating images
        9/ Favourite/Highlight
        10/ Set album profile/cover photo
Progress11/ Sort photos by title, data uploaded, shuffle photos
Done    12/ After Save photo to album, update "In Albums:"
        13/ handle the date_uploaded and date_modified using datetime.strftime('%Y-%m-%d %H:%M:%S')
Done    14/ uuid for photos uploaded via browsing files
        15/ nên hiển thị photos của 1 album theo thứ tự ngược lại: [1, 2, 3] => display 3, 2, 1
"""
dictConfig({
    "version": 1,
    "formatters": {
        "default": {
            "format": "[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
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

API_SVR = os.environ.get('API_SERVER')
pm_init = PhotoManager.InitPM(UPLOAD_FOLDER, "aaaa")
submission_folders = pm_init.submission_folder_dict()


def infer_submission_folder():
    location = pm_init.infer_current_submission_folder(submission_folders)
    if location in submission_folders:
        submission_folders[location] += 1
    else:
        submission_folders[location] = 1
    app.logger.info("current submission folder: {}".format(location))
    return location





@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('index.html')


@app.route('/todo/list', methods=('GET', 'POST'))
def todo_list():
    app.logger.info("You've accessed TODO List")
    if request.method == 'POST':
        content = request.form['content']
        degree = request.form['degree']
        todos.insert_one({'content': content, 'degree': degree})
        return redirect(url_for('todo_list'))

    all_todos = todos.find()
    return render_template('todo-list.html', todos=all_todos)


def save_metadata(_submission_folder, _filename, _title, _description, _courtesy, _hash_md5):
    if not _title:
        _title = "Untitled"
    if not _description:
        _description = _filename
    if not _courtesy:
        _courtesy = "Unknown"
    db.photos.insert_one({'folder': _submission_folder,
                          'filename': _filename,
                          'title': _title,
                          'description': _description,
                          'courtesy': _courtesy,
                          'date_uploaded': datetime.now(TZ_LONDON),
                          'date_modified': datetime.now(TZ_LONDON),
                          'hash_md5': _hash_md5})


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
        if request.form['description'] is not None or not request.form['description']:
            description = request.form['description']
        else:
            description = 'My new album'
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
            if sort_field in ["title",  "amount_photos", "date_created", "date_modified"]:
                is_reverse = not (sort_direction == "down")
                if sort_field == "amount_photos":
                    sorted_albums = sorted(_albums, key=lambda x: len(x['photos']), reverse=is_reverse)
                else:
                    sorted_albums = sorted(_albums, key=lambda x: x[sort_field], reverse=is_reverse)
                view = '_albums-list.html'
        else:
            sorted_albums = sorted(_albums, key=lambda x: len(x['photos']), reverse=True)
        unclassified = {"title": "Unclassified",
                        "description": "Unclassified photos - not belonged to any albums yet.",
                        "amount_photos": 1}
        return render_template(view, albums=sorted_albums, unclassified=unclassified,
                               nb_photo_dict=nb_photos_dict, api_svr=API_SVR)


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

    photos = first_album['photos']
    photo_details = []
    sorted_photo_details = []
    for photo_id in photos:
        photo_doc = db.photos.find_one({"_id": ObjectId(photo_id)})
        if photo_doc is not None:
            photo_details.append(photo_doc)
        else:
            app.logger.info("Photo object id {} was removed.".format(photo_id))

    # Sort the list of photos by the date uploaded
    # sorted_photo_details = sorted(photos_details, key=lambda x: x['date_uploaded'], reverse=True)
    # reverse the list of photos to make sure that we display photos of an album in the chronological order
    photo_details.reverse()
    # After implementing the feature: reordering photos, we want to keep the order we have done on UX/UI
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
        updated_photo_list = []
        if album is not None:
            updated_photo_list: object = album["photos"]
            if (photo_object_id != "") and (photo_object_id not in updated_photo_list):
                updated_photo_list.append(photo_object_id)

        r = db.albums.find_one_and_update(
            {'_id': album.get('_id')},
            {'$set': {
                "photos": updated_photo_list,
                "date_modified": datetime.now(TZ_LONDON)
            }},
            return_document=ReturnDocument.AFTER
        )
        if r.get('_id') is not None:
            updated_albums.append({"path": r['path'], "title": r['title']})

    result = {"updated-albums": updated_albums, "photo-object-id": photo_object_id,
              "photo-folder": photo_folder, "photo-filename": photo_filename}
    return Response(json.dumps(result), mimetype='application/json')


@app.route('/albums/add-photo', methods=['GET', 'POST'])
@app.route('/albums/add-photo/', methods=['POST'])
def albums_add_photo():
    all_albums = db.albums.find()
    # When the client clicks on Add to album button, is will render a select box and a Save button
    return render_template('select_option_albums.html',
                           filename=request.json['photo-filename'], albums=all_albums)


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
            if photo_oid in original_photos:
                original_photos.remove(photo_oid)

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
    album = {"message": "Updating the orders of the photos in the album " + album_object_id}
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
            album = {"message": "Updated the orders of the photos in the album " + album_object_id}

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
    retval = {"message": "Updated completely", "title": album_title, "description": album_description}
    return Response(json.dumps(retval), mimetype='application/json')


@app.route('/albums/view/<path>', methods=('GET', 'POST'))
def albums_view(path):
    if path == "unclassified":
        _photos = photo_unclassified()
        nb_photos = len(_photos)
        is_empty_album = nb_photos == 0
        return render_template('album-view.html', album_path='unclassified',
                               album_title='Unclassified', status="FOUND", photos=_photos, album_object_id="unclassified",
                               nb_photos=nb_photos, is_empty_album=is_empty_album, api_svr=API_SVR)
    status = "FOUND"
    if path is None or path == '':
        return jsonify(message="Path is empty")
    else:
        album = get_album(path)
        if album is None:
            status = "NOT_FOUND"
            return render_template('album-view.html', status=status, message="No such album")
        is_empty_album = not album["photos"]
        view = "album-view.html"
        nb_photos = 0
        if not is_empty_album:
            status = "FOUND"
            nb_photos = len(album["photos_details"])

            if request.method == "POST":
                request_json = request.get_json(silent=True)
                view = request_json['view']
                array_photos_object_ids = request_json['photos-object-ids']
                photos_details = album['photos_details']
                buckets = PhotoManager.create_buckets(photos_details,
                                                      math.ceil(len(array_photos_object_ids) / 3))
                # TODO: using array_photos_object_ids to get the same orders of photos on the current page
                # current_ordered_photos = []
                # for id in array_photos_object_ids:

                return render_template(view, status=status, album=album, album_path=album['path'], album_title=album['title'],
                                       photos=album['photos_details'], buckets=buckets, nb_photos=nb_photos,
                                       album_object_id=album.get("_id"), is_empty_album=is_empty_album, api_svr=API_SVR)

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
                if sort_field in ["title", "date_uploaded", "date_modified"]:
                    photos_details = album["photos_details"]
                    is_reverse = sort_direction == "down"
                    sorted_photos_details = sorted(photos_details, key=lambda x: x[sort_field], reverse=is_reverse)
                    album["photos_details"] = sorted_photos_details
                    view = "_album_view_list.html"

        return render_template(view, status=status, album=album, album_object_id=album.get("_id"),
                               photos=album['photos_details'], album_title=album['title'],
                               album_path=album['path'], nb_photos=nb_photos, is_empty_album=is_empty_album,
                               api_svr=API_SVR)


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


@app.route('/photo/delete', methods=('GET', 'POST'))
def photo_delete():
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


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    if request.method == 'POST':
        file = request.files['photo-upload']
        result = do_upload_photo(request, file)
        app.logger.debug(result)
        return redirect(url_for('photo_list'))

    all_photos = db.photos.find().limit(10).sort([("date_uploaded", pymongo.DESCENDING)])
    all_albums = db.albums.find()
    map_photo_album = {
        "default": {"album-1": "Album 1"}
    }
    _albums = []
    for album in all_albums:
        _albums.append({"path": album, "title": album['title'], "description": album['description']})
        album_detail = get_album(album['path'])
        for photo in album_detail['photos_details']:
            if photo['filename'] in map_photo_album:
                dict_albums = map_photo_album[photo['filename']]
                if album['path'] is not dict_albums:
                    dict_albums[album['path']] = album['title']
            else:
                map_photo_album[photo['filename']] = {album['path']: album['title']}
    # for p in map_photo_album:
    #     print("{}: {}".format(p, map_photo_album[p]))
    # print(_albums)

    return render_template('photo-list.html', albums=_albums,
                           photos=all_photos, map_photo_album=map_photo_album, api_svr=API_SVR)


@app.route('/photo/<path:path>', methods=['GET', 'POST'])
def photo_read(path):
    try:
        return send_from_directory(UPLOAD_FOLDER, path, as_attachment=True)
    except FileNotFoundError as exception:
        app.logger.error("404: File Not Found " + str(exception))


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
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            return jsonify(message="File to be uploaded not found!")
        file = request.files['file']

        if file.filename == '':
            return jsonify(message="File to be uploaded not found or incomplete operation!")
        if file:
            filename = file.filename
            result = do_upload_photo(request, file)
            if "message" in result and result["message"] == "EXISTED":
                return jsonify(message="File existed!")
            return jsonify(
                message="Completed upload files successfully!",
                submission_folder=result['submission_folder'],
                original_filename=filename,
                after_uploaded_filename=filename,
                title=result['title'],
                courtesy=result['origin'])

    return jsonify(message="Under construction or operation is not supported!")


@app.route('/photo/view', methods=['GET', 'POST'])
def photo_view():
    all_photos = db.photos.find().sort([("date_uploaded", pymongo.DESCENDING)])
    # divide 4 because I installed this layout [1]
    # [1] https://www.w3schools.com/howto/howto_js_image_grid.asp
    bucket_size = math.ceil(db.photos.count_documents({}) / 4)
    buckets = PhotoManager.create_buckets(all_photos, bucket_size)

    # after looping over all_photos as a Cursor, all_photos is empty
    all_photos = PhotoManager.flatten_concatenation(buckets)

    return render_template('photo-view.html', photos=all_photos, buckets=buckets, api_svr=API_SVR)


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


def do_upload_photo(client_request, file):
    submission_folder = client_request.headers["Submission-Folder"] \
        if ("Submission-Folder" in request.headers
            and client_request.headers["Submission-Folder"] is not None) else infer_submission_folder()
    UPLOAD_DIR = os.path.join(app.config['UPLOAD_FOLDER'], submission_folder)
    # regenerate a new file for both cases
    filename = str(uuid.uuid4()) + ".jpg"
    if file.filename and file.filename is not None:
        app.logger.info("uploading a local photo...")
        # filename = secure_filename(file.filename)
        # filename = file.filename
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        abs_file_path = os.path.join(str(UPLOAD_DIR), filename)
        file.save(abs_file_path)
        with open(abs_file_path, "rb") as f:
            hash_md5 = hashlib.md5(f.read()).hexdigest()
    else:
        # download the image from the provided image URL
        app.logger.info("Downloading a photo from a remote location...")
        image_url = client_request.headers["Image-URL"] \
            if ("Image-URL" in request.headers
                and client_request.headers["Image-URL"] is not None) else client_request.form['photo-url']
        if image_url is None or image_url == '':
            app.logger.error("Image URL not found!")
            return render_template('photo-list.html', message="Image URL not found!")
        result = do_download_image(UPLOAD_DIR, image_url, filename)
        filename = result["filename"]
        hash_md5 = result["hash_md5"]

    # find any existing photos with hash_md5
    col_photos = db.photos
    docs = col_photos.find_one({"hash_md5": hash_md5})
    if docs is not None:
        app.logger.debug("Photo exists in DB!")
        # move or delete the photo to another folder
        abs_file_path = os.path.join(str(UPLOAD_DIR), filename)
        # https://stackoverflow.com/a/59185523/865603
        pathlib.Path(abs_file_path).unlink(missing_ok=True)
        # TODO: figure out how to use the returned json below on the view
        return jsonify(message="EXISTED", submission_folder=submission_folder)
    else:
        app.logger.info("{} is a new photo.".format(filename))

    # save the file's metadata into MongoDB
    title = client_request.headers["Title"] \
        if ("Title" in request.headers
            and client_request.headers["Title"] is not None) else client_request.form['title']
    title = title if title is not None else filename
    description = client_request.headers["Description"] \
        if ("Description" in request.headers
            and client_request.headers["Description"] is not None) else client_request.form['description']
    description = description if description is not None else filename
    origin = client_request.headers["Photo-Courtesy"] \
        if ("Photo-Courtesy" in request.headers
            and client_request.headers["Photo-Courtesy"] is not None) else client_request.form['courtesy']
    origin = origin if origin is not None else "Unknown"
    save_metadata(submission_folder, filename, title, description, origin, hash_md5)
    return {'submission_folder': submission_folder, 'filename': filename,
            'title': title, 'description': description, 'origin': origin, 'hash_md5': hash_md5}
