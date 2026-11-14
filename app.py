"""Single-owner recording library. Public links are bearer capabilities."""
from contextlib import contextmanager
import hmac
import os
import secrets
import sqlite3
import tempfile
import time
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException


class LibraryFull(HTTPException):
    code = 507
    description = "Library is full. Delete an older recording and retry."


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        OWNER_TOKEN=os.environ.get('OWNER_TOKEN', ''),
        DATA_DIR=os.environ.get('DATA_DIR', './data'),
        MAX_CONTENT_LENGTH=101 * 1024 * 1024,
        MAX_CLIP_BYTES=100 * 1024 * 1024,
        MAX_LIBRARY_BYTES=1024 * 1024 * 1024,
    )
    if config:
        app.config.update(config)
    if len(app.config['OWNER_TOKEN']) < 32:
        raise ValueError('Set OWNER_TOKEN to a random secret of at least 32 characters.')
    data = Path(app.config['DATA_DIR']).resolve()
    data.mkdir(parents=True, exist_ok=True)
    database = data / 'clips.sqlite3'

    @contextmanager
    def connect():
        connection = sqlite3.connect(database, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS clips (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, mime TEXT NOT NULL,
            size INTEGER NOT NULL, created INTEGER NOT NULL)''')

    @app.before_request
    def authenticate():
        if request.path.startswith('/api/'):
            token = request.headers.get('Authorization', '').removeprefix('Bearer ')
            if not hmac.compare_digest(token.encode(), app.config['OWNER_TOKEN'].encode()):
                abort(401, 'Enter the owner key to manage shared recordings.')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "media-src 'self' blob:; img-src 'self' data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    @app.errorhandler(HTTPException)
    def error(exc):
        if request.path.startswith('/api/'):
            return jsonify(error=exc.description), exc.code
        return render_template('error.html', message=exc.description), exc.code

    @app.get('/')
    def home():
        return render_template('index.html')

    @app.get('/health')
    def health():
        return {'ok': True}

    @app.get('/api/clips')
    def clips():
        with connect() as db:
            rows = db.execute('SELECT * FROM clips ORDER BY created DESC, id').fetchall()
        return jsonify([dict(row) for row in rows])

    @app.post('/api/clips')
    def upload():
        title = request.form.get('title', '').strip()
        if not title or len(title) > 120:
            abort(400, 'Add a title of 1–120 characters.')
        file = request.files.get('file')
        if file is None:
            abort(400, 'Choose a WebM or MP4 recording.')
        prefix = file.stream.read(32)
        if prefix.startswith(b'\x1a\x45\xdf\xa3'):
            mime = 'video/webm'
        elif len(prefix) >= 12 and prefix[4:8] == b'ftyp':
            mime = 'video/mp4'
        else:
            abort(415, 'Only WebM and MP4 containers are accepted.')
        clip_id = secrets.token_urlsafe(24)
        destination = data / clip_id
        fd, temporary = tempfile.mkstemp(dir=data, prefix='.upload-')
        size = len(prefix)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(prefix)
                while chunk := file.stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > app.config['MAX_CLIP_BYTES']:
                        abort(413, 'Recording exceeds the 100 MB limit.')
                    stream.write(chunk)
            if size > app.config['MAX_CLIP_BYTES']:
                abort(413, 'Recording exceeds the upload limit.')
            with connect() as db:
                db.execute('BEGIN IMMEDIATE')
                used = db.execute('SELECT COALESCE(SUM(size),0) FROM clips').fetchone()[0]
                if used + size > app.config['MAX_LIBRARY_BYTES']:
                    raise LibraryFull()
                os.replace(temporary, destination)
                db.execute('INSERT INTO clips VALUES (?,?,?,?,?)',
                           (clip_id, title, mime, size, int(time.time())))
            return jsonify(id=clip_id, url='/v/' + clip_id), 201
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        finally:
            Path(temporary).unlink(missing_ok=True)

    def find(clip_id):
        with connect() as db:
            row = db.execute('SELECT * FROM clips WHERE id=?', (clip_id,)).fetchone()
        if row is None:
            abort(404, 'This recording is unavailable or its link was revoked.')
        return row

    @app.get('/v/<clip_id>')
    def watch(clip_id):
        return render_template('watch.html', clip=find(clip_id))

    @app.get('/media/<clip_id>')
    def media(clip_id):
        clip = find(clip_id)
        file = data / clip['id']
        if not file.is_file():
            abort(404, 'The recording file is unavailable.')
        extension = 'webm' if clip['mime'] == 'video/webm' else 'mp4'
        return send_file(file, mimetype=clip['mime'], conditional=True,
                         as_attachment=request.args.get('download') == '1',
                         download_name='recording.' + extension)

    @app.delete('/api/clips/<clip_id>')
    def delete(clip_id):
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT id FROM clips WHERE id=?', (clip_id,)).fetchone()
            if row is None:
                abort(404, 'Recording not found.')
            db.execute('DELETE FROM clips WHERE id=?', (clip_id,))
        (data / row['id']).unlink(missing_ok=True)
        return '', 204

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5120)
