export FLASK_APP=app
export FLASK_ENV=development
export UPLOAD_FOLDER=/Users/tnguyen/ownCloud/MyBusiness/data/photo-manager
export UPLOAD_FOLDER=/home/tnguyen/Documents/MyBusiness/PhotoManager/photodb
#export UPLOAD_FOLDER=/home/tnguyen/Documents/MyBusiness/PhotoManager/mygallery
#flask run --host=0.0.0.0 --port=5500 --debug >> logs/run.log
python app.py
#gunicorn --config gunicorn_config.py app:app
