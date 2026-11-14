"""Run browser acceptance on a disposable local library, never the owner's server."""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SERVER = """
import os
from pathlib import Path
from werkzeug.serving import make_server
from app import create_app
server = make_server('127.0.0.1', 0, create_app(), threaded=True)
Path(os.environ['CLIP_PORT_FILE']).write_text(str(server.server_port))
server.serve_forever()
"""


def main():
    with tempfile.TemporaryDirectory(prefix='clip-local-acceptance-') as directory:
        folder = Path(directory)
        port_file = folder / 'port'
        artifacts = folder / 'artifacts'
        artifacts.mkdir()
        env = dict(os.environ, OWNER_TOKEN=secrets.token_urlsafe(32),
                   DATA_DIR=str(folder / 'data'), CLIP_PORT_FILE=str(port_file),
                   CLIP_ARTIFACT_DIR=str(artifacts))
        with (folder / 'server.log').open('w+') as log:
            server = subprocess.Popen([sys.executable, '-c', SERVER], cwd=ROOT,
                                      env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 20
                while not port_file.exists():
                    if server.poll() is not None:
                        raise RuntimeError('Isolated test server exited before startup.')
                    if time.monotonic() > deadline:
                        raise RuntimeError('Isolated test server did not start within 20 seconds.')
                    time.sleep(0.1)
                env['TEST_URL'] = 'http://127.0.0.1:' + port_file.read_text()
                with urllib.request.urlopen(env['TEST_URL'], timeout=10) as response:
                    if response.status != 200:
                        raise RuntimeError('Isolated server readiness check failed.')
                subprocess.run(['node', 'browser.test.cjs'], cwd=ROOT, env=env,
                               timeout=120, check=True)
                print('PASS: isolated local acceptance; temporary key, media and browser artifacts cleaned up.')
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == '__main__':
    main()
