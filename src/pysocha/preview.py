import mimetypes
from flask import Flask, make_response
from functools import update_wrapper

# Yes, I know, globals bad, it's a preview dev tool
previewServer = Flask(__name__, static_url_path='')
_startPage = 'index.html'

def nocache(f):
    def new_func(*args, **kwargs):
        resp = make_response(f(*args, **kwargs))
        resp.cache_control.no_cache = True
        return resp
    return update_wrapper(new_func, f)

@previewServer.after_request
def nocache_response(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Expires'] = '-1'
    return response

@previewServer.route('/hello')
def hello_world():
    return 'Hello World!'

@previewServer.route('/')
@nocache
def root():
    return previewServer.send_static_file(_startPage)

def makePreviewServer(static_folder: str = 'generated', start_page: str = 'index.html', extension: str = 'html'):
    global previewServer, _startPage
    mimetypes.add_type('text/html', extension)
    previewServer.static_folder=static_folder
    _startPage = start_page
    return previewServer
