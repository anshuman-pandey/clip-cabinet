#!/usr/bin/env python3
"""Test an already-built image using isolated disposable containers and volumes."""
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request

IMAGE = os.environ.get('CLIP_TEST_IMAGE', 'clip-cabinet:acceptance')
prefix = 'clip-acceptance-' + secrets.token_hex(5)
token = secrets.token_urlsafe(32)
containers, volumes = [], []


def docker(*args, **kwargs):
    return subprocess.check_output(['docker', *args], **kwargs)


def create(suffix):
    name, volume = prefix + suffix, prefix + suffix + '-data'
    docker('volume', 'create', volume)
    volumes.append(volume)
    docker('create', '--name', name, '-p', '127.0.0.1::5120',
           '-e', 'OWNER_TOKEN', '-v', volume + ':/app/data', IMAGE,
           env={**os.environ, 'OWNER_TOKEN': token})
    containers.append(name)
    return name


def start(name):
    docker('start', name)
    port = json.loads(docker('inspect', name))[0]['NetworkSettings']['Ports']['5120/tcp'][0]['HostPort']
    base = 'http://127.0.0.1:' + port
    for _ in range(120):
        try:
            if request(base, '/health')[0] == 200:
                return base
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.25)
    raise RuntimeError('Container did not become healthy')


def request(base, path, method='GET', data=None, headers=None):
    req = urllib.request.Request(base+path, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def upload(base, title):
    # Container storage fixture, intentionally not a playable recording.
    # The separate browser suite tests real MediaRecorder media and playback.
    boundary = 'clipfixture'
    data = (f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\n{title}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="sample.webm"\r\n'
            'Content-Type: video/webm\r\n\r\n').encode() + b'\x1a\x45\xdf\xa3fixture' + f'\r\n--{boundary}--\r\n'.encode()
    code, body, _ = request(base, '/api/clips', 'POST', data,
                           {'Authorization': 'Bearer '+token, 'Content-Type': 'multipart/form-data; boundary='+boundary})
    assert code == 201, (code, body)
    return json.loads(body)['id']


try:
    original = create('-original')
    base = start(original)
    assert docker('exec', original, 'id', '-u').strip() == b'10001'
    assert request(base, '/api/clips')[0] == 401
    keep = upload(base, 'Persist across restart')
    revoke = upload(base, 'Revoke before backup')
    code, body, _ = request(base, '/media/'+keep, headers={'Range': 'bytes=0-3'})
    assert code == 206 and body == b'\x1a\x45\xdf\xa3'
    assert request(base, '/api/clips/'+revoke, 'DELETE', headers={'Authorization':'Bearer '+token})[0] == 204
    docker('stop', original)
    backup = docker('cp', original+':/app/data/.', '-')
    base = start(original)
    assert request(base, '/media/'+keep)[0] == 200
    assert request(base, '/media/'+revoke)[0] == 404
    restored = create('-restored')
    subprocess.run(['docker', 'cp', '-a', '-', restored+':/app/data/'], input=backup, check=True)
    restored_base = start(restored)
    assert request(restored_base, '/media/'+keep)[0] == 200
    assert request(restored_base, '/v/'+revoke)[0] == 404
    upload(restored_base, 'Restored database remains writable')
    if os.environ.get('CLIP_TEST_BROWSER') == '1':
        subprocess.run(['node', 'browser.test.cjs'], check=True,
                       env={**os.environ, 'TEST_URL': base, 'OWNER_TOKEN': token})
    print('PASS: UID 10001, owner auth, upload, byte ranges, revocation, restart persistence, stopped-volume backup and restore, restored writes.')
finally:
    for name in reversed(containers):
        subprocess.run(['docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, check=False)
    for name in reversed(volumes):
        subprocess.run(['docker', 'volume', 'rm', name], stdout=subprocess.DEVNULL, check=False)
