# Clip Cabinet

Record a short screen walkthrough, preview it, download it, and optionally share it from your own server. An open-source, single-owner alternative to **Loom** for the recording-and-link workflow. MIT licensed; no third-party analytics or video storage. This is a local candidate, not a publicly released service.

## Run locally

Python 3.12+:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export OWNER_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export DATA_DIR=./data
python app.py
```

Open http://127.0.0.1:5120. Use the generated `OWNER_TOKEN` in the owner-key field when uploading or managing links. Keep that token private; it grants full library access. Restart with the same environment configuration to retain owner access. A different token rotates access without changing existing viewer links.

1. Choose screen & record; select a screen, window or tab in the browser picker. Microphone narration is optional and asks for separate permission.
2. Stop, preview the recording and download a copy. Nothing uploads automatically.
3. Add a title and owner key, then Upload & create link.
4. Open the link in another browser. Use Revoke & delete in the library to remove the hosted file and stop future access.

A browser-supported WebM or MP4 file can also be imported. Capture automatically stops at five minutes or approximately 100 MB; the final chunk may take it over the upload limit, in which case a local download remains available. Uploads are capped at 100 MB and the hosted library at 1 GB. Browser memory holds the current recording; refreshing loses unsaved work.

## Self-host

Run behind an HTTPS reverse proxy. Screen capture works on localhost for development; remote recording requires HTTPS. Example application command:

```sh
gunicorn --bind 0.0.0.0:5120 --workers 2 --threads 4 --timeout 120 'app:create_app()'
```

Docker:

```sh
docker build -t clip-cabinet .
docker volume create clip-cabinet-data
docker run --rm -p 127.0.0.1:5120:5120 -e OWNER_TOKEN \
  -v clip-cabinet-data:/app/data clip-cabinet
```

If your network uses a private certificate authority, supply its trusted CA bundle for the build without disabling certificate checks:

```sh
docker build --secret id=pip_ca,src=/path/to/trusted-ca-bundle.pem -t clip-cabinet .
```

The CA secret is available only to the dependency-install build step and is not copied into the final image. Normal networks need no secret.

The container runs as UID 10001. Bind mounts must be writable by that UID. Configure the reverse proxy to accept 101 MB bodies and a sufficient upload timeout, preserve Range requests, and avoid logging bearer link paths. Do not cache viewer pages or media. No forwarded host is used to generate absolute links: the browser uses the current origin. Keep the app on one host with local persistent SQLite/file storage. Back up the whole data directory while the app is stopped; restore it together. A crash can leave an orphan upload/file consuming disk; review files absent from the database before removing them. Monitor available disk space.

Shared links are unlisted bearer links, **not authenticated viewer access**. Anyone holding one can watch and download. Revocation cannot stop an already-open transfer or recall downloaded copies. File signatures are checked for supported containers; this is not a malware scanner or full media validator. Upload access belongs only to the trusted owner. Set rate limits at your proxy for internet deployment.

## Scope and comparison

This covers local screen recording, optional microphone, playback/download, and self-hosted revocable sharing. It does not offer Loom’s full product: no camera overlay, system audio, editing, transcription, comments, teams, or analytics. No pricing, performance or feature-parity claims are made. Current competitor features/pricing must be verified before expanding the comparison.

## Validation

```sh
pip install pytest==9.2.0
python -m pytest -q
npm ci
npx playwright install chromium
# Start an isolated temporary server/library and run browser acceptance:
python scripts/check_local.py
```

`TEST_URL` overrides localhost; `CHROMIUM_PATH` selects an installed browser. The browser test supplies synthetic screen frames, then uses real MediaRecorder and checks playback, download, upload, anonymous viewer playback, revocation, file import, missing owner key and permission-denial recovery. It creates and deletes a recording on the target server. Seven server tests verify auth, escaped titles, byte ranges, quota concurrency, upload limits, persistence and deletion. Container acceptance is also reproducible:

```sh
docker build -t clip-cabinet:acceptance .
CLIP_TEST_BROWSER=1 python3 scripts/docker_acceptance.py
```

This creates isolated temporary containers and named volumes, checks non-root UID, auth, upload, byte ranges, restart persistence, revocation, stopped-volume backup/restore and post-restore writes, then runs browser acceptance against the container. It removes only its own test containers/volumes afterward. Container storage checks use a synthetic container-header fixture; real playable video is exercised by the browser suite. The CI workflow runs both suites. Remote CI has not run yet.

Real browser picker, microphone hardware and hosted HTTPS acceptance remain release gates. See `artifacts/validation.json`.

## Distribution

Publish this as its own repository, release package and demo. Demonstrate one complete “record a bug reproduction → share with a maintainer → revoke” workflow using synthetic content. Start with a useful integration tutorial in an owned project’s contributor docs; consider external self-hosting listings only after public installation works and their rules permit it. No external submissions or promotional posts have been made.

## Owner launch handoff

[HANDOFF.md](HANDOFF.md) identifies runnable artifacts, exact manual screen-picker/microphone checks, existing versus freshly run validation, and the prefilled repository form. Publishing source, releases or hosting requires separate product-specific authorization.
