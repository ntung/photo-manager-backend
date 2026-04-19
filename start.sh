export FLASK_APP=app
export FLASK_ENV=development
# UPLOAD_FOLDER is set in .env and loaded by python-dotenv at startup
#flask run --host=0.0.0.0 --port=5500 --debug >> logs/run.log
#python app.py
gunicorn app.app:app \
    --config gunicorn_config.py \
    --reload
# OR
#gunicorn --bind 0.0.0.0:5500 \
#  --workers 17 \
#  --certfile=cert.pem \
#  --keyfile=key.pem \
#  --access-logfile - --error-logfile - \
#  app:app
