# Bailey Course Mirrored Offsite Archive

This workspace contains a mirrored offsite archive of Mike Bailey's OSU home page and the requested course sites. The generated standalone archive is in `archive/`; open `archive/index.html` to start.

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

The archive home page adds a mirrored-offsite objective and course index above the original home-page content. Course pages and nested HTML pages, including directory-index pages such as `glman/`, are wrapped in the provided `theme-showcase` light/dark/cyber scaffold, with local OSU links rewritten to archived files where possible.

## Files

- `archive/` - final standalone archive, currently 131 themed HTML pages and 2,310 files. This is ignored by Git.
- `hosting/` - generated Firebase Hosting payload, currently 1,008 files / 49 MB. It keeps HTML, theme files, local Cyber fonts, and small assets on `profbailey.web.app`; larger archive assets are linked from Cloud Storage. This is ignored by Git.
- `archive/index.html` - generated home page and main entry point.
- `archive/MANIFEST.md` - generated list of themed HTML pages.
- `mirror/` - raw Wget mirror used as generator input. This is ignored by Git and can be packaged for object storage.
- `tools/build_archive.py` - rebuilds `archive/` from `mirror/` and the scaffold files.
- `tools/build_hosting_site.py` - builds the lightweight Firebase Hosting directory from `archive/`.
- `tools/package_mirror.sh` - creates `dist/mirror.zip` with maximum ZIP compression for bucket upload.
- `tools/apply_cloud_config.sh` - applies repeatable Cloud Storage cache, storage-class, lifecycle, and public/private access policy.
- `tools/disable_unused_services.sh` - disables Google Cloud APIs that are not used by this static archive after basic resource checks.
- `infra/` - versioned Cloud Storage lifecycle policy files.
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
python3 tools/build_hosting_site.py
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

The full archive includes multi-GiB course binaries, videos, PDFs, and ZIP/TAR files. The deployment uses Firebase Hosting for the browsable site and Cloud Storage for the complete asset payload:

```bash
python3 tools/build_archive.py
python3 tools/build_hosting_site.py
gcloud storage rsync -r archive gs://profbailey-archive-assets
gcloud storage buckets add-iam-policy-binding gs://profbailey-archive-assets --member=allUsers --role=roles/storage.objectViewer
tools/apply_cloud_config.sh
firebase deploy --project profbailey --only hosting
```

Package the raw mirror and upload it to the public mirror bucket:

```bash
tools/package_mirror.sh
gcloud storage cp dist/mirror.zip gs://profbailey-mirror/mirror.zip
gcloud storage buckets add-iam-policy-binding gs://profbailey-mirror --member=allUsers --role=roles/storage.objectViewer
tools/apply_cloud_config.sh
```

The Firebase Hosting config sends `X-Robots-Tag: noindex, nofollow, noarchive` and the generated archive includes `robots.txt` with `Disallow: /`. These reduce compliant crawler indexing. They do not make content private.

## Private Storage

To make the Cloud Storage buckets private and non-anonymous, remove public IAM and enforce public access prevention:

```bash
gcloud storage buckets remove-iam-policy-binding gs://profbailey-archive-assets --member=allUsers --role=roles/storage.objectViewer
gcloud storage buckets remove-iam-policy-binding gs://profbailey-mirror --member=allUsers --role=roles/storage.objectViewer
gcloud storage buckets update gs://profbailey-archive-assets --public-access-prevention=enforced
gcloud storage buckets update gs://profbailey-mirror --public-access-prevention=enforced
```

Doing this will break the current public `https://storage.googleapis.com/...` archive links. To keep downloads available without anonymous access, put the asset delivery behind an authenticated path, such as an IAP-protected Cloud Run download proxy, Firebase Auth plus signed short-lived URLs, or another authenticated CDN/proxy. Plain Firebase Hosting and direct public Cloud Storage URLs are public surfaces.

The same bucket policy script can enforce private storage once an authenticated delivery path exists:

```bash
PRIVATE_STORAGE=1 tools/apply_cloud_config.sh
```

## Cloud Surface

Repeatable infrastructure commands:

```bash
tools/apply_cloud_config.sh
tools/disable_unused_services.sh
```

Storage policy:

- `gs://profbailey-archive-assets` stays Standard by default for frequently used class material.
- Large/cold suffixes such as videos, archives, object files, blend files, and data files move to Nearline after 30 days and Coldline after 90 days.
- `gs://profbailey-mirror` uses Archive storage by default, and `mirror.zip` is set to Archive because it is a cold backup package.

The service disable script keeps this project scoped to Firebase Hosting, Cloud Storage, Firebase management, Resource Manager, Logging, Monitoring, Service Usage, and required Google-managed services. It checks for Firebase apps, BigQuery datasets, and Pub/Sub resources before disabling the unused API set. Some core services, including `bigquery.googleapis.com`, `cloudtrace.googleapis.com`, `datastore.googleapis.com`, and `sql-component.googleapis.com`, are intentionally not forced off because Service Usage reports `cloudapis.googleapis.com` as a dependent service; the BigQuery companion APIs are disabled when unused.

## Web Surface

Known script and frame exceptions for security headers:

- WebGL sample page: `webgl/sample.html` loads local `WebGL/Webgl-Utils.js`, `WebGL/InitShaders.js`, `WebGL/GlMatrix.js`, `webgl/sampledata.js`, and `webgl/sample.js`.
- WebGL helper scripts: `webgl/sample-shaders.js` and `webgl/sample-ui.js` replace the original inline shader and jQuery UI setup so CSP can use `script-src 'self'`.
- Theme script: every themed HTML page loads local `assets/theme-toggle.js`.
- Third-party iframe: `cs550/lookingglassquilts.html` embeds two `https://blocks.glass/embed/...` frames. These are allowed by CSP `frame-src`; all iframes are generated with lazy loading, strict referrer policy, and a sandbox.

Cloud Storage buckets:

- `gs://profbailey-archive-assets`
- `gs://profbailey-mirror`

Mirror ZIP URL:

```text
https://storage.googleapis.com/profbailey-mirror/mirror.zip
```

## Verification

Final local-link audit:

- HTML pages: 131
- Local URL references checked: 3,409
- Live external `cs.oregonstate.edu/~mjb` / `web.engr.oregonstate.edu/~mjb` references: 0
- Remaining missing local references: 20
- External non-`~mjb` links intentionally left external: 1,190

The remaining missing local references correspond to source-side 404/403 responses:

- `cgeducation/ShadersBookSecond/openglstatemachine.pdf` - 404
- `cs519/Obj/lighting.{frag,geom,glib,vert}` - 403
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
