# Bailey Course Mirrored Offsite Archive

This workspace contains a mirrored offsite archive of Mike Bailey's OSU home page and the requested course sites. The generated archive is in `archive/`; open `archive/index.html` to start.

Public archive: https://profbailey.web.app/

GitHub repository: https://github.com/denuoweb/profbailey

## Scope

Mirrored source roots:

- https://web.engr.oregonstate.edu/~mjb/
- https://web.engr.oregonstate.edu/~mjb/cs491/
- https://web.engr.oregonstate.edu/~mjb/cs575/
- https://web.engr.oregonstate.edu/~mjb/cs557/
- https://web.engr.oregonstate.edu/~mjb/cs553/
- https://web.engr.oregonstate.edu/~mjb/cs519v/
- https://web.engr.oregonstate.edu/~mjb/cs550/

The archive home page adds a mirrored-offsite objective and course index above the original home-page content. Course pages and nested HTML pages are wrapped in the provided `theme-showcase` light/dark/cyber scaffold, with local OSU links rewritten to archived files where possible.

## Files

- `archive/` - final standalone archive, currently 106 themed HTML pages and 1,838 files. This is ignored by Git and deployed to Firebase Hosting.
- `archive/index.html` - generated home page and main entry point.
- `archive/MANIFEST.md` - generated list of themed HTML pages.
- `mirror/` - raw Wget mirror used as generator input. This is ignored by Git and can be packaged for object storage.
- `tools/build_archive.py` - rebuilds `archive/` from `mirror/` and the scaffold files.
- `tools/package_mirror.sh` - creates `dist/mirror.zip` with maximum ZIP compression for bucket upload.
- `firebase.json` and `.firebaserc` - Firebase Hosting configuration for project `profbailey`.
- `logs/` - fetch logs and final link-audit reports.
- `scaffold/` - unpacked source theme from `theme-showcase.zip`.

## Rebuild

Install the Python dependency if needed:

```bash
python3 -m pip install -r requirements.txt
```

Regenerate the themed archive from the current mirror:

```bash
python3 tools/build_archive.py
```

Serve locally for browser testing:

```bash
python3 -m http.server 8000 --directory archive
```

Then open:

```text
http://localhost:8000/
```

## Deploy

The archive includes course binaries and executable-extension files, so Firebase Hosting requires the project to be on the Blaze billing plan before deployment. After upgrading `profbailey` to Blaze, deploy the generated archive to Firebase Hosting:

```bash
firebase deploy --project profbailey --only hosting
```

After billing is upgraded to Blaze, package the raw mirror and upload it to a public Cloud Storage bucket:

```bash
tools/package_mirror.sh
gcloud storage buckets create gs://profbailey-mirror --project=profbailey --location=us-west1 --uniform-bucket-level-access
gcloud storage cp dist/mirror.zip gs://profbailey-mirror/mirror.zip
gcloud storage buckets add-iam-policy-binding gs://profbailey-mirror --member=allUsers --role=roles/storage.objectViewer
```

Mirror ZIP URL:

```text
https://storage.googleapis.com/profbailey-mirror/mirror.zip
```

## Verification

Final local-link audit:

- HTML pages: 106
- Local URL references checked: 3,654
- Live external `cs.oregonstate.edu/~mjb` / `web.engr.oregonstate.edu/~mjb` references: 0
- Remaining missing local references: 15
- External non-`~mjb` links intentionally left external: 1,006

The remaining missing local references correspond to source-side 404/403 responses:

- `cs519v/openglstatemachine.pdf` - 404
- `cs550/PDFs/SinCos.1pp.pdf` - 404
- `cs550/Handouts/GettingStarted.{1,2,4,6}pp.pdf` - 404
- `cs553/Handouts/stencilexamples.2pp.pdf` - 404
- `cs557/Obj/lighting.{frag,geom,glib,vert}` - 403
- `cs557/PDFs/Project.Notes.457.557.1pp.pdf` - 404
- `cs575/Handouts/Project.Notes.1pp.pdf` - 404
- `vulkan/openglstatemachine.pdf` - 404
- `vulkan/opengl45-quick-reference-card.pdf` - 404

Detailed reports are in `logs/final-missing-links.tsv` and `logs/final-external-links.tsv`.
