import io
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import create_app

TOKEN = 'test-' + 'a'*40
VIDEO = b'\x1a\x45\xdf\xa3' + b'synthetic-container-fixture'*20

@pytest.fixture
def app(tmp_path):
    return create_app({'TESTING':True,'DATA_DIR':str(tmp_path),'OWNER_TOKEN':TOKEN})

def auth():
    return {'Authorization':'Bearer '+TOKEN}

def upload(client, title='A walkthrough', data=VIDEO):
    return client.post('/api/clips',headers=auth(),data={'title':title,'file':(io.BytesIO(data),'clip.webm')})

def test_requires_strong_owner_key(tmp_path):
    with pytest.raises(ValueError):create_app({'OWNER_TOKEN':'short','DATA_DIR':str(tmp_path)})

def test_owner_auth_and_no_cross_origin(app):
    c=app.test_client()
    assert c.get('/').status_code==200
    for method,path in [('get','/api/clips'),('post','/api/clips'),('delete','/api/clips/nope')]:
        assert getattr(c,method)(path).status_code==401
    assert 'Access-Control-Allow-Origin' not in c.get('/api/clips',headers=auth()).headers

def test_upload_watch_range_download_revoke(app):
    c=app.test_client();r=upload(c);assert r.status_code==201
    clip=r.json['id'];assert len(clip)==32
    assert c.get('/api/clips',headers=auth()).json[0]['title']=='A walkthrough'
    assert c.get(r.json['url']).status_code==200
    r=c.get('/media/'+clip,headers={'Range':'bytes=0-3'});assert r.status_code==206;assert r.data==VIDEO[:4]
    r=c.get('/media/'+clip+'?download=1');assert 'attachment' in r.headers['Content-Disposition']
    assert c.delete('/api/clips/'+clip,headers=auth()).status_code==204
    assert c.get('/v/'+clip).status_code==404
    assert c.get('/media/'+clip).status_code==404
    assert c.get('/api/clips',headers=auth()).json==[]

def test_title_is_escaped_and_invalid_container_rejected(app):
    c=app.test_client();r=upload(c,'<script>alert(1)</script>')
    assert b'<script>alert(1)</script>' not in c.get(r.json['url']).data
    assert upload(c,data=b'<html>no video</html>').status_code==415
    assert upload(c,title=' ').status_code==400
    assert upload(c,title='x'*121).status_code==400

def test_quota_is_atomic_and_failed_uploads_removed(app):
    app.config['MAX_LIBRARY_BYTES']=len(VIDEO)
    def send(_):
        with app.test_client() as c:return upload(c).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,range(2)))
    assert sorted(codes)==[201,507]
    from pathlib import Path
    files=list(Path(app.config['DATA_DIR']).iterdir())
    assert len([p for p in files if p.name!='clips.sqlite3'])==1

def test_upload_limit_and_missing_file(app):
    app.config['MAX_CLIP_BYTES']=20
    c=app.test_client();assert upload(c).status_code==413
    assert c.post('/api/clips',headers=auth(),data={'title':'test'}).status_code==400
    assert c.get('/api/clips',headers=auth()).json==[]

def test_persistence_and_headers(app):
    c=app.test_client();clip=upload(c).json['id']
    other=create_app(dict(app.config));r=other.test_client().get('/media/'+clip)
    assert r.data==VIDEO
    assert r.headers['Cache-Control']=='no-store'
    assert r.headers['X-Content-Type-Options']=='nosniff'
    assert r.headers['Referrer-Policy']=='no-referrer'
    assert "frame-ancestors 'none'" in r.headers['Content-Security-Policy']
