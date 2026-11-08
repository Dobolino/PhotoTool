"""The local review serves only its session, declared assets and photo IDs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import http.client
from io import BytesIO
import json
from pathlib import Path
import socket
from urllib.parse import urlsplit

from PIL import Image
import pytest

from photobook_curator.models import Photo
from photobook_curator.review_export import plan_from_photos


@pytest.fixture
def endpoint(tmp_path):
    from photobook_curator.modern_review import ReviewServer
    from photobook_curator.modern_review_session import ReviewSession
    photos = []
    for index in range(3):
        source = tmp_path / 'originals' / f'photo-{index}.jpg'
        source.parent.mkdir(parents=True, exist_ok=True)
        exif = Image.Exif()
        if index == 1:
            exif[274] = 6  # Real camera orientation: display this photo vertically.
        Image.new('RGB', (480, 320), (40 + index * 20, 100, 200)).save(source, exif=exif)
        photos.append(Photo(source, source.name, datetime_taken=datetime(2026, 5, 1, 10, index),
            region='Kyoto', chapter_folder='01_Kyoto/hauptteil', is_selected=index == 0,
            is_candidate=True, book_position=1 if index == 0 else None))
    session = ReviewSession(photos, plan_from_photos(photos), tmp_path / 'project')
    server = ReviewServer(session)
    url = server.start()
    parts = urlsplit(url)
    yield dict(server=server, session=session, url=url, parts=parts,
               origin=f'{parts.scheme}://{parts.netloc}', prefix=parts.path)
    server.close()
    session.close()


def request(endpoint, path='api/state', *, method='GET', body=None, headers=None):
    connection = http.client.HTTPConnection(endpoint['parts'].hostname, endpoint['parts'].port, timeout=3)
    headers = dict(headers or {})
    if isinstance(body, dict):
        body = json.dumps(body).encode()
        headers.setdefault('Content-Type', 'application/json')
    connection.request(method, endpoint['prefix'] + path, body=body, headers=headers)
    response = connection.getresponse()
    content = response.read()
    result = response.status, dict(response.getheaders()), content
    connection.close()
    return result


def test_loopback_token_and_host_are_required_for_metadata_and_photos(endpoint):
    assert endpoint['parts'].scheme == 'http'
    assert endpoint['parts'].hostname == '127.0.0.1'
    assert len(endpoint['prefix'].strip('/')) >= 32
    status, headers, raw = request(endpoint)
    assert status == 200
    assert headers['Content-Type'].startswith('application/json')
    assert len(json.loads(raw)['photos']) == 3

    for path in ('api/state', 'image/0?edge=160'):
        status, _, _ = request(endpoint, path, headers={'Host': 'example.invalid'})
        assert status in {400, 403, 421}
        connection = http.client.HTTPConnection('127.0.0.1', endpoint['parts'].port, timeout=3)
        connection.request('GET', '/not-the-session/' + path)
        response = connection.getresponse()
        assert response.status in {401, 403, 404}
        assert b'photo-0.jpg' not in response.read()
        connection.close()


def test_post_rejects_cross_origin_non_json_and_oversized_or_invalid_bodies(endpoint):
    before = endpoint['session'].snapshot()
    payload = {'action': 'toggle', 'id': 1, 'selected': True}
    for origin in (None, 'null', 'https://example.invalid', 'http://localhost:1234'):
        headers = {} if origin is None else {'Origin': origin}
        status, _, _ = request(endpoint, 'api/action', method='POST', body=payload, headers=headers)
        assert status == 403
    for body, content_type in ((b'{}', 'text/plain'), (b'not json', 'application/json'),
                               (b'[]', 'application/json')):
        status, _, _ = request(endpoint, 'api/action', method='POST', body=body,
            headers={'Origin': endpoint['origin'], 'Content-Type': content_type})
        assert status in {400, 415}
    for length, expected in (('65537', {413}), ('-1', {400}), ('invalid', {400})):
        status, _, _ = request(endpoint, 'api/action', method='POST', body=b'', headers={
            'Origin': endpoint['origin'], 'Content-Type': 'application/json', 'Content-Length': length})
        assert status in expected
    connection = http.client.HTTPConnection('127.0.0.1', endpoint['parts'].port, timeout=3)
    connection.request('POST', endpoint['prefix'] + 'api/action', body=b'{}', headers={
        'Origin': endpoint['origin'], 'Content-Type': 'application/json', 'Content-Length': '10'})
    connection.sock.shutdown(socket.SHUT_WR)
    response = connection.getresponse()
    assert response.status == 400
    response.read()
    connection.close()
    assert endpoint['session'].snapshot()['kept'] == before['kept']


def test_static_paths_and_image_parameters_cannot_read_arbitrary_files(endpoint):
    status, headers, index = request(endpoint, '')
    assert status == 200 and b'PhotoTool' in index
    csp = headers.get('Content-Security-Policy', '')
    assert "script-src 'self'" in csp
    assert 'unsafe-inline' not in csp.split('script-src', 1)[1].split(';', 1)[0]
    assert headers.get('X-Content-Type-Options') == 'nosniff'
    assert headers.get('Referrer-Policy') == 'no-referrer'
    for path in ('../pyproject.toml', '%2e%2e/pyproject.toml', 'image/../../etc/passwd',
                 'image/%2fetc%2fpasswd', 'image/-1', 'image/999', 'data/settings.json'):
        status, _, content = request(endpoint, path)
        assert status in {400, 404}, path
        assert b'root:' not in content
    status, _, _ = request(endpoint, 'image/1?edge=999999')
    assert status == 400
    # Omitted images are still available for judgement, always in colour.
    status, headers, image_bytes = request(endpoint, 'image/1?edge=160')
    assert status == 200 and headers['Content-Type'].startswith('image/')
    with Image.open(BytesIO(image_bytes)) as image:
        assert max(image.size) <= 160
        assert image.height > image.width, 'HTTP previews must apply the original EXIF orientation'
        red, green, blue = image.convert('RGB').getpixel((0, 0))
        assert max(red, green, blue) - min(red, green, blue) > 50


def test_competing_clients_cannot_silently_overwrite_selection(endpoint):
    revision = endpoint['session'].snapshot()['revision']
    def toggle(index):
        return request(endpoint, 'api/action', method='POST', body={
            'action': 'toggle', 'id': index, 'selected': True, 'expected_revision': revision,
        }, headers={'Origin': endpoint['origin']})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(toggle, (1, 2)))
    assert sorted(status for status, _, _ in results) == [200, 409]
    assert len(endpoint['session'].snapshot()['kept']) == 2
    stale = next(json.loads(content) for status, _, content in results if status == 409)
    assert isinstance(stale.get('error'), str)
    assert stale['state']['revision'] > revision


def test_closed_session_server_no_longer_accepts_requests(endpoint):
    endpoint['server'].close()
    with pytest.raises(OSError):
        request(endpoint)
