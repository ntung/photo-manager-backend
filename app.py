import math
import os
import tempfile
import uuid
import requests
import bson
import bson.json_util
from bson import ObjectId
from flask import Flask
from flask import jsonify, render_template, request, url_for, redirect, send_from_directory
from flask_cors import CORS
from pymongo import MongoClient

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
                       'title': _title, 'description': _description, 'photo_courtesy': _photo_courtesy})


@app.route('/photo/albums', methods=('GET', 'POST'))
def photo_albums():
    if request.method == 'POST':
        # file = request.files['photo-upload']
        # file = request.form['photo-upload']
        # title = request.form['title']
        # description = request.form['description']
        # courtesy = request.form['courtesy']
        # do_upload_load(request, file)
        return redirect(url_for('photo_albums'))
    elif request.method == 'GET':

        db_albums = db.albums
        all_albums = db_albums.find()
        return render_template('photo-albums.html', albums=all_albums)


@app.route('/albums', defaults={'path': None}, methods=('GET', 'POST'))
@app.route('/albums/<path>', methods=('GET', 'POST'))
def albums(path):
    albums = db.albums
    if path is None:
        all_albums = albums.find()
        docs_as_extended_json = bson.json_util.dumps(all_albums)
        # bson.json_util.loads(docs_as_extended_json)
        return docs_as_extended_json
    else:
        result = albums.find({"path": path})
        first_album = result[0]
        photos = first_album['photos']
        # print(photos)
        photo_details = []
        for photo_id in photos:
            photo_doc = db.photos.find_one({"_id": ObjectId(photo_id)})
            photo_details.append(photo_doc)
            # print(bson.json_util.dumps(photo_doc))

        first_album["photos_details"] = photo_details
        json_result = bson.json_util.dumps(first_album)
        # print("JSON result " + json_result)
        return json_result


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    if request.method == 'POST':
        file = request.files['photo-upload']
        do_upload_load(request, file)
        return redirect(url_for('photo_list'))

    photos = db.photos
    all_photos = photos.find()

    api_svr = os.environ.get('API_SERVER')
    return render_template('photo-list.html', photos=all_photos, api_svr=api_svr)


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

        print("Bucket {} - Photo {}: {}".format(b, i, photo["filename"]))

    # append the last bucket regardless of no matter how it has
    if counter <= bucket_size:
        buckets.append(bucket)

    print("Nb. of all photos {}".format(i))

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
    print(res.status_code)
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
    description = client_request.headers["Description"] \
        if ("Description" in request.headers
            and client_request.headers["Description"] is not None) else client_request.form['description']
    origin = client_request.headers["Photo-Courtesy"] \
        if ("Photo-Courtesy" in request.headers
            and client_request.headers["Photo-Courtesy"] is not None) else client_request.form['courtesy']
    save_metadata(submission_folder, filename, title, description, origin)
    return {'submission_folder': submission_folder, 'filename': filename,
            'title': title, 'description': description, 'origin': origin}
