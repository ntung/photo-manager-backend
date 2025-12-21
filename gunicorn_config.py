import multiprocessing
import os


workers = multiprocessing.cpu_count() * 2 + 1
# workers = int(os.environ.get('GUNICORN_PROCESSES', '4'))

threads = int(os.environ.get('GUNICORN_THREADS', '8'))

# timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))

bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5500')

keyfile = 'key.pem'
certfile = 'cert.pem'

forwarded_allow_ips = '*'

secure_scheme_headers = { 'X-Forwarded-Proto': 'https' }

# Logging
accesslog = 'logs/access.log'
errorlog = 'logs/error.log'
