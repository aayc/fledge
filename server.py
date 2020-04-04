from flask import Flask
from flask import request
import webbrowser
import logging

def mini_server(token, callback):
    app = Flask(__name__)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @app.route('/')
    def index():
        return auth

    @app.route('/download_keys', methods=['POST'])
    def download_keys():
        keys = request.get_json()
        shutdown_server()
        callback(keys)
        return {}

    def shutdown_server():
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            raise RuntimeError('Not running with the Werkzeug Server')
        func()

    with open("auth.html", 'r') as f:
        auth = f.readlines()
        for i in range(len(auth)):
            if auth[i].strip().startswith("var publicKey"):
                auth[i] = f"var publicKey = '{token}'\n"
        auth = "".join(auth)

    webbrowser.open("http://localhost:5000/")
    app.run(debug=False)
