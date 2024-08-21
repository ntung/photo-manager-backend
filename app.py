import os
import tempfile

from flask import Flask
from flask import jsonify, render_template, request, url_for, redirect
from pymongo import MongoClient

TMP_BM = tempfile.gettempdir() + "/photo-manager/upload"
os.makedirs(TMP_BM, exist_ok=True)
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', TMP_BM)

client = MongoClient('localhost', 27017)
db = client.flask_db
todos = db.todos

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


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


@app.route('/photo/list', methods=('GET', 'POST'))
def photo_list():
    if request.method == 'POST':
        file = request.files['photo-upload']
        # file = request.form['photo-upload']
        title = request.form['title']
        description = request.form['description']
        courtesy = request.form['courtesy']
        do_upload_load(request, file)
        return redirect(url_for('photo_list'))

    photos = db.photos
    all_photos = photos.find()
    return render_template('photo-list.html', photos=all_photos)


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


def do_upload_load(client_request, file):
    #flash('No selected file')
    #return redirect(request.url)
    #if file and allowed_file(file.filename):
    submission_folder = client_request.headers["Submission-Folder"] \
        if ("Submission-Folder" in request.headers
            and client_request.headers["Submission-Folder"] is not None) else "aaaa"  # TODO: tinh cai nay sau
    filename = file.filename  #secure_filename(file.filename)
    UPLOAD_DIR = app.config['UPLOAD_FOLDER'] + "/" + submission_folder
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    file.save(os.path.join(UPLOAD_DIR, filename))

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
