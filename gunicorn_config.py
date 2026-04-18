import multiprocessing
import os

# Use Uvicorn workers
# worker_class = "uvicorn.workers.UvicornWorker"

config_kwargs = {
  "no_server_header": True,
  "no_date_header": True
}

workers = multiprocessing.cpu_count() * 2 + 1
# workers = int(os.environ.get('GUNICORN_PROCESSES', '4'))

# Remove this - not compatible with UvicornWorker
# Each Uvicorn worker already handles multiple concurrent requests efficiently 
# through async/await, so we don't need threads. 
# threads = int(os.environ.get('GUNICORN_THREADS', '8'))

# timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))

bind = os.environ.get('GUNICORN_BIND', '0.0.0.0:5500')
keyfile = 'certs/localhost+2-key.pem'
certfile = 'certs/localhost+2-cert.pem'

forwarded_allow_ips = '*'

secure_scheme_headers = { 'X-Forwarded-Proto': 'https' }

# Logging
accesslog = 'logs/access.log'
errorlog = 'logs/error.log'
