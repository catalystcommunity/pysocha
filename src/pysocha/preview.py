import mimetypes
import os
from flask import Flask, make_response, request
from functools import update_wrapper

# Yes, I know, globals bad, it's a preview dev tool
previewServer = Flask(__name__, static_url_path='')
_startPage = 'index.html'
_extension = '.html'

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

@previewServer.errorhandler(404)
def directory_index(error):
    """
    Serve the index file of a directory, the way a real web server does. Search
    pages live at a path such as /search/, so the preview has to find them too.
    The static route already claims every path, so this runs after it fails.
    """
    subpath = request.path.strip('/')
    if subpath:
        candidate = subpath + '/index' + _extension
        if os.path.isfile(os.path.join(previewServer.static_folder, candidate)):
            return previewServer.send_static_file(candidate)
    return error

#: Types the preview must get right, whatever the machine says.
#:
#: On Windows the mimetypes module reads the registry, which has long mapped
#: .js to text/plain. A browser refuses to run a module served as text/plain,
#: so a search page that imports one fails on Windows and nowhere else. Setting
#: these after the module loads its own tables makes every platform agree.
_REQUIRED_TYPES = {
    '.js': 'text/javascript',
    '.mjs': 'text/javascript',
    '.json': 'application/json',
    '.wasm': 'application/wasm',
    '.css': 'text/css',
}


def makePreviewServer(static_folder: str = 'generated', start_page: str = 'index.html', extension: str = '.html'):
    global previewServer, _startPage, _extension
    mimetypes.add_type('text/html', extension)
    for suffix, mime_type in _REQUIRED_TYPES.items():
        mimetypes.add_type(mime_type, suffix)
    previewServer.static_folder=static_folder
    _startPage = start_page
    _extension = extension if extension.startswith('.') else '.' + extension
    return previewServer
