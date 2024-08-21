import os, requests, tempfile
from flask import Flask, jsonify, render_template, request, url_for, redirect
from pymongo import MongoClient

from flask import Flask
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
    if request.method == 'POST':
        content = request.form['content']
        degree = request.form['degree']
        todos.insert_one({'content': content, 'degree': degree})
        return redirect(url_for('index'))

    all_todos = todos.find()
    return render_template('index.html', todos=all_todos)


def save_matadata(_submission_folder, _filename, _title, _description, _photo_courtesy):
    photos = db.photos
    photos.insert_one({ 'folder': _submission_folder, 'filename': _filename, 
        'title': _title, 'description': _description, 'photo_courtesy': _photo_courtesy })



@app.route('/upload', methods=('GET', 'POST'))
def upload():
    '''
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
    '''
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
        #if file and allowed_file(file.filename):
            submission_folder = request.headers["Submission-Folder"]
            filename = file.filename #secure_filename(file.filename)
            UPLOAD_DIR = app.config['UPLOAD_FOLDER'] + "/" + submission_folder
            os.makedirs(UPLOAD_DIR, exist_ok=True)            
            file.save(os.path.join(UPLOAD_DIR, filename))
        
            # save the file's metadata into MongoDB
            title = request.headers["Title"] if request.headers["Title"] is not None else filename
            description = request.headers["Description"] if request.headers["Description"] is not None else filename
            origin = request.headers["Photo-Courtesy"] if request.headers["Photo-Courtesy"] is not None else filename
            save_matadata(submission_folder, filename, title, description, origin)
            return jsonify(
                message="Completed upload files successfully!",
                submission_folder=submission_folder,
                original_filename=file.filename, 
                after_uploaded_filename=filename, 
                title=title, 
                photo_courtesy=origin)
        
    return jsonify(message="Under construction or operation is not supported!")