export FLASK_APP=app
export FLASK_ENV=development
export UPLOAD_FOLDER=/Users/tnguyen/ownCloud/MyBusiness/data/PM/photodb-files
#export UPLOAD_FOLDER=/home/tnguyen/Documents/MyBusiness/PhotoManager/photodb
#export UPLOAD_FOLDER=/home/tnguyen/Documents/MyBusiness/PhotoManager/mygallery
#flask run --host=0.0.0.0 --port=5500 --debug >> logs/run.log
#python app.py
gunicorn --config gunicorn_config.py app.app:app
# OR
#gunicorn --bind 0.0.0.0:5500 \
#  --workers 17 \
#  --certfile=cert.pem \
#  --keyfile=key.pem \
#  --access-logfile - --error-logfile - \
#  app:app