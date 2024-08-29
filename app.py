import json
import math
import os
import tempfile
import uuid
from datetime import datetime

import pymongo
import requests
import bson
import bson.json_util
from bson import ObjectId
from flask import Flask, Response
from flask import jsonify, render_template, request, url_for, redirect, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient, ReturnDocument
from slugify import slugify

TMP_BM = tempfile.gettempdir() + "/photo-manager/upload"
os.makedirs(TMP_BM, exist_ok=True)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', TMP_BM)

client = MongoClient('localhost', 27017)
db = client.flask_db
todos = db.todos

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type: application/json'

API_SVR = os.environ.get('API_SERVER')


@app.route('/', methods=('GET', 'POST'))
def index():
    return render_template('index.html')


@app.route('/todo/list', methods=('GET', 'POST'))
def todo_list():
    if request.method == 'POST':
        content = request.form['content']
        degree = request.form['degree']
        todos.insert_one({'content': content, 'degree': degree})
        return redirect(url_for('todo_list'))

    all_todos = todos.find()
    return render_template('todo-list.html', todos=all_todos)


def save_metadata(_submission_folder, _filename, _title, _description, _photo_courtesy):
    photos = db.photos
    photos.insert_one({'folder': _submission_folder, 'filename': _filename,
                       'title': _title, 'description': _description, 'photo_courtesy': _photo_courtesy,
                       'date_uploaded': datetime.now().astimezone(),
                       'date_modified': datetime.now().astimezone()})


@app.route('/photo/albums', methods=('GET', 'POST'))
def photo_albums():
    db_albums = db.albums

    if request.method == 'POST':
        file = request.files['cover']
        if file.content_length > 0:
            print("TODO: implement to store this photo")
        title = request.form['title'] if request.form['title'] is not None else 'Untitled'
        description = request.form['description'] if request.form['description'] is not None else 'My new album'
        if title == "Untitled":
            all_untitled_albums = db_albums.find({
                "title": {'$regex': '^Untitled'}}
            ).limit(1).sort('title', pymongo.ASCENDING)
            if all_untitled_albums is None:
                title = "Untitled 001"
            else:
                for album in all_untitled_albums:
                    print(album['title'])
        path = slugify(title)
        r = db.albums.insert_one({'path': path, 'title': title, 'description': description, 'photos': []})
        print(r)
        return redirect(url_for('photo_albums'))
    elif request.method == 'GET':
        all_albums = db_albums.find()
        return render_template('photo-albums.html', albums=all_albums, api_svr=API_SVR)


@app.route('/albums', defaults={'path': None}, methods=('GET', 'POST'))
@app.route('/albums/', defaults={'path': None}, methods=('GET', 'POST'))
@app.route('/albums/<path>', methods=('GET', 'POST'))
def albums(path):
    dbalbums = db.albums
    if path is None:
        all_albums = dbalbums.find()
        docs_as_extended_json = bson.json_util.dumps(all_albums)
        # bson.json_util.loads(docs_as_extended_json)
        return docs_as_extended_json
    else:
        first_album = get_album(path)
        json_result = bson.json_util.dumps(first_album)
        return json_result


def get_album(path):
    dbalbums = db.albums
    result = dbalbums.find({"path": path})
    first_album = result[0]
    photos = first_album['photos']
    photo_details = []
    for photo_id in photos:
        photo_doc = db.photos.find_one({"_id": ObjectId(photo_id)})
        photo_details.append(photo_doc)

    first_album["photos_details"] = photo_details

    return first_album


@app.route('/photo/save-photo-to-albums', methods=['GET', 'POST'])
@app.route('/photo/save-photo-to-albums/', methods=['POST'])
def save_photo_to_albums():
    request_json = request.get_json(silent=True)
    # print(request_json)
    photo_object_id = request_json['photo-object-id']
    photo_folder = request_json['photo-folder']
    photo_filename = request_json['photo-filename']


    # album_path = request_json['album_path']
    # photo_object_id = request_json['photo_object_id']
    # print("{} - {}".format(album_path, photo_object_id))
    #
    newly_added_albums = request_json['newly-added-albums']
    updated_albums = []
    for album in newly_added_albums:
        album = get_album(album['path'])
        updated_photo_list = []
        if album is not None:
            # print("photo object id: ".format(photo_object_id))
            updated_photo_list: object = album["photos"]
            if (photo_object_id is not None and photo_folder != ""
                    and photo_object_id not in updated_photo_list):
                updated_photo_list.append(photo_object_id)
        # print("Updated photo list: {}".format(updated_photo_list))
        r = db.albums.find_one_and_update(
            {'_id': album.get('_id')}, {'$set': {"photos": updated_photo_list}},
            return_document=ReturnDocument.AFTER
        )
        # print(r)
        if r.get('_id') is not None:
            updated_albums.append({"path": r['path'], "title": r['title']})
        result = {"updated-albums": updated_albums, "photo-object-id": photo_object_id}
    return Response(json.dumps(result),  mimetype='application/json')


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
    retval = {}
    if (album is not None) and (album.get('photos') is not None):
        original_photos = album['photos']
        tobe_removed_photos = request_json['removed-photos']
        for photo in tobe_removed_photos:
            original_photos.remove(photo['photo-object-id'])

        # save the update
        r = db.albums.find_one_and_update(
            {'_id': album.get('_id')}, {'$set': {"photos": original_photos}},
            return_document=ReturnDocument.AFTER
        )
        if r.get("_id") is not None:
            retval = {"path": r['path'], "title": r['title']}

    return Response(json.dumps(retval),  mimetype='application/json')


@app.route('/albums/view/<path>', methods=('GET', 'POST'))
def albums_view(path):
    if path is None:
        pass
    else:
        album = get_album(path)
        is_empty_album = not album["photos"]
        api_svr = os.environ.get('API_SERVER')
        return render_template('album-view.html',
                               album=album, is_empty_album=is_empty_album, api_svr=api_svr)


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    if request.method == 'POST':
        file = request.files['photo-upload']
        do_upload_load(request, file)
        return redirect(url_for('photo_list'))

    photos = db.photos
    all_photos = photos.find().sort([("date_uploaded", pymongo.DESCENDING)])
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
    api_svr = os.environ.get('API_SERVER')
    return render_template('photo-list.html', albums=_albums,
                           photos=all_photos, map_photo_album=map_photo_album, api_svr=api_svr)


@app.route('/photo/<path:path>', methods=['GET', 'POST'])
def photo_read(path):
    try:
        return send_from_directory(UPLOAD_FOLDER, path, as_attachment=True)
    except FileNotFoundError as fnfe:
        print("404: File Not Found " + fnfe)


@app.route('/photo/upload', methods=('GET', 'POST'))
def photo_upload():
    """
    persisted_token = None
    username = None
    if "username" in request.headers:
        username = request.headers["username"]
        if not username:
            return jsonify(message="Cannot verify your authorisation! Please check your request!")
        else:
            persisted_token = look_up_token(username)
    if not persisted_token:
        return jsonify(
                message="You may haven't requested an access token yet.")
    """
    '''
    token = None
    if "Authorization" in request.headers:
        auth = request.headers["Authorization"]
        token = auth.split(" ")[1]
    if not token:
        return {
            "message": "Authentication token is missing!",
            "data": None,
            "error": "Unauthorized"
        }
    if token != look_up_token(token):
        return jsonify(message="Unauthorized to perform this task!!!")
    '''

    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            #flash('No file part')
            #return redirect(request.url)
            return jsonify(message="File to be uploaded not found!")
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            #flash('No selected file')
            #return redirect(request.url)
            return jsonify(message="File to be uploaded not found or incomplete operation!")
        if file:
            filename = file.filename
            result = do_upload_load(request, file)
            return jsonify(
                message="Completed upload files successfully!",
                submission_folder=result['submission_folder'],
                original_filename=filename,
                after_uploaded_filename=filename,
                title=result['title'],
                photo_courtesy=result['origin'])

    return jsonify(message="Under construction or operation is not supported!")


# TODO: check md5 preventing duplicated images

@app.route('/photo/view', methods=['GET', 'POST'])
def photo_view():
    dbphotos = db.photos
    all_photos = dbphotos.find()
    bucket_size = math.ceil(dbphotos.count_documents({}) / 4)
    buckets = []
    """
    counter = 0 -> the last bucket will have less or equal the number of photos than the bucket size
    counter = 1 -> the first bucket will have less or equal the number of photos than the bucket size
    """
    counter = 0
    bucket = []
    i = 0
    b = 1
    for photo in all_photos:
        i += 1
        if counter == bucket_size:
            # REMEMBER: always adding the last photo to the current bucket!!!
            bucket.append(photo)
            buckets.append(bucket)
            # then reset the bucket and the counters
            bucket = []
            counter = 1
            b += 1
        else:
            bucket.append(photo)
            counter += 1

        # print("Bucket {} - Photo {}: {}".format(b, i, photo["filename"]))

    # append the last bucket regardless of no matter how it has
    if counter <= bucket_size:
        buckets.append(bucket)

    # after looping over all_photos as a Cursor, all_photos is empty
    all_photos = flatten_concatenation(buckets)
    api_svr = os.environ.get('API_SERVER')

    return render_template('photo-view.html', photos=all_photos, buckets=buckets, api_svr=api_svr)


# https://realpython.com/python-flatten-list/
def flatten_concatenation(matrix):
    flat_list = []
    for row in matrix:
        flat_list += row

    return flat_list


def do_download_image(storage_location, image_url):
    # this function is working like a charm for Facebook images
    res = requests.get(image_url, stream=True)
    # Request the image and save it:
    out_filename = str(uuid.uuid4()) + ".jpg"
    with open(storage_location + "/" + out_filename, "wb") as f:
        f.write(res.content)
    return out_filename


def do_upload_load(client_request, file):
    #flash('No selected file')
    #return redirect(request.url)
    #if file and allowed_file(file.filename):
    submission_folder = client_request.headers["Submission-Folder"] \
        if ("Submission-Folder" in request.headers
            and client_request.headers["Submission-Folder"] is not None) else "aaaa"  # TODO: tinh cai nay sau
    UPLOAD_DIR = app.config['UPLOAD_FOLDER'] + "/" + submission_folder

    if file.content_length > 0:
        filename = file.filename  #secure_filename(file.filename)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file.save(os.path.join(UPLOAD_DIR, filename))
    else:
        # download the image from the provided image URL
        image_url = client_request.headers["Image-URL"] \
            if ("Image-URL" in request.headers
                and client_request.headers["Image-URL"] is not None) else client_request.form['photo-url']
        filename = do_download_image(UPLOAD_DIR, image_url)

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
    save_metadata(submission_folder, filename, title, description, origin)
    return {'submission_folder': submission_folder, 'filename': filename,
            'title': title, 'description': description, 'origin': origin}
