#!/usr/bin/env python3
from __future__ import annotations

import html as html_escape
import os
import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import SplitResult, unquote, urlsplit, urlunsplit

from lxml import etree, html


ROOT = Path("mirror/web.engr.oregonstate.edu/~mjb")
OUT = Path("archive")
SCAFFOLD = Path("scaffold")
ASSETS = OUT / "assets"
THEME_STORAGE_KEY = "mjb-course-archive-theme"
SOURCE_BASE = "https://web.engr.oregonstate.edu/~mjb/"
ARCHIVE_DATE = "May 28, 2026"
PUBLIC_ARCHIVE_URL = "https://profbailey.web.app/"
GITHUB_URL = "https://github.com/denuoweb/profbailey"
MIRROR_DOWNLOAD_URL = "https://storage.googleapis.com/profbailey-mirror/mirror.zip"

COURSES = [
    ("cs491", "CS 491", "CS Skills for Simulation and Game Programming"),
    ("cs575", "CS 475 / 575", "Parallel Programming"),
    ("cs557", "CS 457 / 557", "Computer Graphics Shaders"),
    ("cs553", "CS 453 / 553", "Scientific Visualization"),
    ("cs519v", "CS 419v / 519v", "Vulkan"),
    ("cs550", "CS 450 / 550", "Introduction to Computer Graphics"),
]

LOCAL_HOSTS = {
    "web.engr.oregonstate.edu",
    "cs.oregonstate.edu",
    "eecs.oregonstate.edu",
}

URL_ATTRS = {
    "a": ("href",),
    "area": ("href",),
    "img": ("src", "longdesc"),
    "script": ("src",),
    "link": ("href",),
    "iframe": ("src",),
    "embed": ("src",),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "object": ("data",),
    "body": ("background",),
    "td": ("background",),
    "th": ("background",),
}

PRESENTATION_ATTRS = {
    "background",
    "bgcolor",
    "text",
    "link",
    "vlink",
    "alink",
    "color",
    "face",
}


def looks_like_html(path: Path) -> bool:
    if path.suffix.lower() in {".html", ".htm"}:
        return True
    if path.suffix:
        return False
    try:
        sample = path.read_bytes()[:8192].decode("utf-8", errors="ignore").lower()
    except OSError:
        return False
    return any(marker in sample for marker in ("<!doctype html", "<html", "<head", "<body", "<title"))


def html_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*")
        if path.is_file() and looks_like_html(path)
    )


def rel_posix(path: Path) -> str:
    return path.as_posix()


def root_relative(path: Path) -> PurePosixPath:
    return PurePosixPath(rel_posix(path.relative_to(ROOT)))


def out_relative(path: Path) -> PurePosixPath:
    return PurePosixPath(rel_posix(path.relative_to(OUT)))


def output_path_for(source_path: Path, *, home_index: bool = False) -> Path:
    if home_index:
        return OUT / "index.html"
    return OUT / source_path.relative_to(ROOT)


def ensure_index_path(path: PurePosixPath) -> PurePosixPath:
    text = path.as_posix()
    if not text or text == ".":
        return PurePosixPath("index.html")
    if text.endswith("/"):
        return PurePosixPath(text + "index.html")
    if (ROOT / text).is_dir():
        return PurePosixPath(text) / "index.html"
    if text in {course for course, _, _ in COURSES}:
        return PurePosixPath(text) / "index.html"
    if text == "WebMjb":
        return PurePosixPath("WebMjb/mjb.html")
    return path


def to_archive_rel(target: PurePosixPath, output_path: Path) -> str:
    output_dir = out_relative(output_path.parent)
    if output_dir.as_posix() == ".":
        start = "."
    else:
        start = output_dir.as_posix()
    rel = os.path.relpath(target.as_posix(), start=start)
    return rel.replace(os.sep, "/")


def is_skippable_url(value: str) -> bool:
    lowered = value.strip().lower()
    return (
        not lowered
        or lowered.startswith("#")
        or lowered.startswith("mailto:")
        or lowered.startswith("tel:")
        or lowered.startswith("javascript:")
        or lowered.startswith("data:")
    )


def normalize_local_abs_path(parts: SplitResult) -> PurePosixPath | None:
    host = parts.netloc.lower()
    if host not in LOCAL_HOSTS:
        return None

    path = unquote(parts.path)
    if path in {"/~mjb", "/~mjb/"}:
        return PurePosixPath("index.html")
    if not path.startswith("/~mjb/"):
        return None

    rel = path.removeprefix("/~mjb/")
    if not rel:
        return PurePosixPath("index.html")

    return ensure_index_path(PurePosixPath(rel))


def rewrite_one_url(value: str, source_path: Path, output_path: Path) -> str:
    value = value.strip()
    if is_skippable_url(value):
        return value

    # srcset values are comma-separated URL plus descriptor pairs.
    if "," in value and re.search(r"\s+\d+[wx](?:\s*,|$)", value):
        rewritten_parts = []
        for chunk in value.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            bits = chunk.split()
            bits[0] = rewrite_one_url(bits[0], source_path, output_path)
            rewritten_parts.append(" ".join(bits))
        return ", ".join(rewritten_parts)

    parts = urlsplit(value)
    fragment = parts.fragment
    query = parts.query

    if parts.scheme in {"http", "https"}:
        local_target = normalize_local_abs_path(parts)
        if local_target is None:
            return value
        rewritten = to_archive_rel(local_target, output_path)
        if query:
            rewritten += "?" + query
        if fragment:
            rewritten += "#" + fragment
        return rewritten

    if parts.scheme:
        return value

    if parts.path.startswith("/"):
        fake_absolute = SplitResult("https", "web.engr.oregonstate.edu", parts.path, parts.query, parts.fragment)
        local_target = normalize_local_abs_path(fake_absolute)
        if local_target is not None:
            rewritten = to_archive_rel(local_target, output_path)
            if query:
                rewritten += "?" + query
            if fragment:
                rewritten += "#" + fragment
            return rewritten
        return urlunsplit(fake_absolute)

    tilde_match = re.match(r"^(?:\.\./)+~mjb/(.*)$", parts.path)
    if tilde_match:
        target = ensure_index_path(PurePosixPath(unquote(tilde_match.group(1))))
        rewritten = to_archive_rel(target, output_path)
        if query:
            rewritten += "?" + query
        if fragment:
            rewritten += "#" + fragment
        return rewritten

    source_rel = root_relative(source_path)
    source_dir = source_rel.parent
    joined = posixpath.normpath(posixpath.join(source_dir.as_posix(), unquote(parts.path)))
    if joined.startswith("../"):
        return value

    target = ensure_index_path(PurePosixPath(joined))
    rewritten = to_archive_rel(target, output_path)
    if query:
        rewritten += "?" + query
    if fragment:
        rewritten += "#" + fragment
    return rewritten


def clean_and_rewrite_tree(body: etree._Element, source_path: Path, output_path: Path) -> None:
    for comment in body.xpath(".//comment()"):
        parent = comment.getparent()
        if parent is not None:
            parent.remove(comment)

    for image in list(body.iter("img")):
        src = image.attrib.get("src", "")
        if "/icons/" in src or src.startswith("icons/") or src.startswith("../icons/"):
            image.drop_tree()

    for node in body.iter():
        if not isinstance(node.tag, str):
            continue

        for attr in URL_ATTRS.get(node.tag.lower(), ()):
            if attr in node.attrib:
                node.attrib[attr] = rewrite_one_url(node.attrib[attr], source_path, output_path)

        for attr in list(node.attrib):
            if attr.lower() in PRESENTATION_ATTRS:
                del node.attrib[attr]

        if "style" in node.attrib:
            style = node.attrib["style"]
            style = re.sub(r"(?:^|;)\s*(background(?:-color|-image)?|color|font-family)\s*:[^;]*;?", ";", style, flags=re.I)
            style = ";".join(part.strip() for part in style.split(";") if part.strip())
            if style:
                node.attrib["style"] = style
            else:
                del node.attrib["style"]


def parse_source(source_path: Path) -> tuple[str, str]:
    parser = html.HTMLParser(encoding="utf-8")
    document = html.parse(str(source_path), parser).getroot()

    title_el = document.find(".//title")
    title = ""
    if title_el is not None:
        title = " ".join(title_el.text_content().split())
    if not title:
        for selector in ("h1", "h2", "h3"):
            candidate = document.find(f".//{selector}")
            if candidate is not None:
                title = " ".join(candidate.text_content().split())
                break
    if not title:
        title = source_path.name

    body = document.find(".//body")
    if body is None:
        body = document

    return title, body


def body_inner_html(body: etree._Element) -> str:
    pieces: list[str] = []
    if body.text and body.text.strip():
        pieces.append(html_escape.escape(body.text))
    for child in body:
        pieces.append(html.tostring(child, encoding="unicode", method="html"))
    return "\n".join(pieces)


def rel_asset(output_path: Path, asset_name: str) -> str:
    return to_archive_rel(PurePosixPath("assets") / asset_name, output_path)


def course_nav(output_path: Path, current_course: str | None = None, current_home: bool = False) -> str:
    links = [
        (
            "Home",
            to_archive_rel(PurePosixPath("index.html"), output_path),
            current_home,
        )
    ]
    for slug, label, _ in COURSES:
        links.append(
            (
                label,
                to_archive_rel(PurePosixPath(slug) / "index.html", output_path),
                current_course == slug,
            )
        )

    rendered = []
    for label, href, current in links:
        aria = ' aria-current="page"' if current else ""
        rendered.append(f'<a href="{html_escape.escape(href)}"{aria}>{html_escape.escape(label)}</a>')
    return "\n      ".join(rendered)


def archive_intro(output_path: Path) -> str:
    course_items = []
    for slug, label, description in COURSES:
        href = to_archive_rel(PurePosixPath(slug) / "index.html", output_path)
        source = SOURCE_BASE + slug + "/"
        course_items.append(
            f"""
            <article class="course-card">
              <h3><a href="{html_escape.escape(href)}">{html_escape.escape(label)}</a></h3>
              <p>{html_escape.escape(description)}</p>
              <p class="source-link">Source: {html_escape.escape(source)}</p>
            </article>
            """.strip()
        )

    return f"""
    <section class="showcase-section archive-objective" aria-labelledby="archive-objective-heading">
      <h2 id="archive-objective-heading">Mirrored Offsite Archive</h2>
      <p>
        This mirrored offsite archive preserves Mike Bailey's OSU home page and selected course resources as a backup
        outside the legacy COE public_html / LAMP hosting environment. It is intended to keep the course content, links,
        images, downloads, and related material available after the public-facing hosting transition.
      </p>
      <p>
        COE's notice says COE-hosted public_html / LAMP content will no longer be publicly accessible from the internet
        beginning Monday, June 26, 2028. This archive was generated from the public source pages on {ARCHIVE_DATE}.
      </p>
      <p class="archive-links">
        <a href="{html_escape.escape(GITHUB_URL)}" target="_blank" rel="noopener">GitHub repository</a>
        <a href="{html_escape.escape(PUBLIC_ARCHIVE_URL)}" target="_blank" rel="noopener">Public archive</a>
        <a href="{html_escape.escape(MIRROR_DOWNLOAD_URL)}" target="_blank" rel="noopener">Raw mirror ZIP</a>
      </p>
      <div class="course-grid" aria-label="Archived classes">
        {"".join(course_items)}
      </div>
    </section>
    """


def current_course_for(source_path: Path) -> str | None:
    rel = root_relative(source_path)
    if rel.parts:
        first = rel.parts[0]
        if first in {course for course, _, _ in COURSES}:
            return first
    return None


def source_url_for(source_path: Path) -> str:
    rel = root_relative(source_path)
    if rel.name.lower() == "index.html":
        parent = rel.parent.as_posix()
        if parent == ".":
            return SOURCE_BASE
        return SOURCE_BASE + parent + "/"
    return SOURCE_BASE + rel.as_posix()


def render_page(source_path: Path, output_path: Path, *, home_index: bool = False) -> None:
    title, body = parse_source(source_path)
    clean_and_rewrite_tree(body, source_path, output_path)
    content = body_inner_html(body)
    escaped_title = html_escape.escape(title)
    source_url = source_url_for(source_path)
    home = home_index
    current_course = None if home else current_course_for(source_path)
    intro = archive_intro(output_path) if home_index else ""
    source_note = (
        SOURCE_BASE
        if home_index
        else source_url
    )
    escaped_source_note = html_escape.escape(source_note)
    escaped_github_url = html_escape.escape(GITHUB_URL)
    page = f"""<!DOCTYPE html>
<html lang="en" data-theme="light" data-theme-storage-key="{THEME_STORAGE_KEY}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Mirrored offsite archive of {escaped_title}.">
  <title>{escaped_title} | Bailey Mirrored Offsite Archive</title>
  <link rel="stylesheet" href="{rel_asset(output_path, "theme-tokens.css")}">
  <link rel="stylesheet" href="{rel_asset(output_path, "archive.css")}">
  <script type="module" src="{rel_asset(output_path, "theme-toggle.js")}"></script>
</head>
<body>
  <main class="showcase archive-page" id="main-content">
    <div class="theme-toolbar" data-theme-controls role="group" aria-label="Theme switcher">
      <button type="button" data-theme="light" aria-pressed="true">Light</button>
      <button type="button" data-theme="dark" aria-pressed="false">Dark</button>
      <button type="button" data-theme="cyber" aria-pressed="false">Cyber</button>
    </div>

    <nav class="archive-nav" aria-label="Archive sections">
      {course_nav(output_path, current_course=current_course, current_home=home)}
    </nav>

    <header class="showcase-section archive-title">
      <p class="eyebrow">Mirrored Offsite Archive</p>
      <h1>{escaped_title}</h1>
      <p class="lede">
        Archived from <a href="{escaped_source_note}" target="_blank" rel="noopener">{escaped_source_note}</a> on {ARCHIVE_DATE}.
        Project source: <a href="{escaped_github_url}" target="_blank" rel="noopener">GitHub</a>.
      </p>
    </header>

    {intro}

    <section class="showcase-section legacy-content" id="archived-content" aria-label="Archived page content">
{content}
    </section>
  </main>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page, encoding="utf-8")


def write_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    tokens = (SCAFFOLD / "theme-tokens.css").read_text(encoding="utf-8")
    tokens = tokens.replace('"Fraunces", Georgia, serif', 'Georgia, "Times New Roman", serif')
    tokens = tokens.replace('"Source Sans 3", "Segoe UI", sans-serif', '"Segoe UI", Roboto, Helvetica, Arial, sans-serif')
    (ASSETS / "theme-tokens.css").write_text(tokens, encoding="utf-8")
    shutil.copy2(SCAFFOLD / "theme-toggle.js", ASSETS / "theme-toggle.js")
    if (SCAFFOLD / "fonts").exists():
        font_assets = ASSETS / "fonts"
        font_assets.mkdir(parents=True, exist_ok=True)
        for font_path in (SCAFFOLD / "fonts").glob("*"):
            if font_path.suffix.lower() in {".ttf", ".woff", ".woff2"}:
                shutil.copy2(font_path, font_assets / font_path.name)

    base_css = (SCAFFOLD / "theme-showcase.css").read_text(encoding="utf-8")
    base_css = re.sub(r'@import url\("[^"]+"\);\s*', "", base_css)
    archive_css = base_css + """

h1 {
  font-size: 3rem;
}

h2 {
  font-size: 2.1rem;
}

h3 {
  font-size: 1.35rem;
}

.archive-page {
  max-width: 78rem;
}

.archive-title {
  text-align: center;
}

.eyebrow {
  margin: 0 0 0.35rem;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.archive-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
  margin-top: 1rem;
}

.archive-nav a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.45rem 0.8rem;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--surface-1);
  box-shadow: var(--shadow-soft);
  font-weight: 700;
}

.archive-nav a[aria-current="page"] {
  border-color: var(--accent-color);
  color: var(--accent-color);
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

.archive-links {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  margin-top: 1rem;
}

.archive-links a {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0.85rem;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--surface-2);
  font-weight: 700;
}

.archive-objective,
.legacy-content {
  padding: 1.25rem;
  border: 1px solid var(--border-color);
  border-radius: 1.25rem;
  background: var(--surface-1);
  box-shadow: var(--shadow-soft);
}

.course-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.course-card {
  min-width: 0;
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: 1rem;
  background: var(--surface-2);
}

.course-card h3 {
  font-size: 1.25rem;
}

.source-link {
  color: var(--text-muted);
  font-size: 0.95rem;
  overflow-wrap: anywhere;
}

.legacy-content {
  overflow-x: auto;
}

.legacy-content center {
  display: block;
  text-align: center;
}

.legacy-content img,
.legacy-content video,
.legacy-content object,
.legacy-content embed,
.legacy-content iframe {
  max-width: 100%;
  height: auto;
}

.legacy-content img[align="right"] {
  margin: 0 0 1rem 1rem;
}

.legacy-content img[align="left"] {
  margin: 0 1rem 1rem 0;
}

.legacy-content table {
  width: auto;
  max-width: 100%;
  margin: 0.75rem 0;
  border-collapse: collapse;
}

.legacy-content td,
.legacy-content th {
  min-width: 0;
}

.legacy-content table[border="0"] td,
.legacy-content table:not([border]) td {
  border-color: transparent;
}

.legacy-content hr {
  clear: both;
}

.legacy-content font,
.legacy-content font[color] {
  color: inherit !important;
  font-family: inherit !important;
}

.legacy-content a {
  overflow-wrap: anywhere;
}

a:not([href]),
a:not([href]):visited,
a:not([href]):hover,
a:not([href]):focus-visible {
  color: inherit;
  text-decoration: none;
  cursor: default;
  outline: 0;
}

.legacy-content pre {
  white-space: pre-wrap;
}

@media (max-width: 900px) {
  .course-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  h1 {
    font-size: 2.25rem;
  }

  h2 {
    font-size: 1.65rem;
  }

  h3 {
    font-size: 1.2rem;
  }
}
"""
    (ASSETS / "archive.css").write_text(archive_css, encoding="utf-8")


TEXT_LOCAL_URL_RE = re.compile(
    r"https?://(?:web\.engr\.oregonstate\.edu|cs\.oregonstate\.edu|eecs\.oregonstate\.edu)/~mjb/[^\s\"'<>)]*",
    re.I,
)


def rewrite_text_asset_urls() -> None:
    for path in OUT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".css", ".js"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        source_equivalent = ROOT / path.relative_to(OUT)

        def replace_url(match: re.Match[str]) -> str:
            return rewrite_one_url(match.group(0), source_equivalent, path)

        rewritten = TEXT_LOCAL_URL_RE.sub(replace_url, text)
        if rewritten != text:
            path.write_text(rewritten, encoding="utf-8")


def copy_mirror() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT, OUT)


def write_manifest(pages: list[Path]) -> None:
    lines = [
        "# Generated Archive Manifest",
        "",
        f"Generated: {ARCHIVE_DATE}",
        f"Source root: {SOURCE_BASE}",
        "",
        "## Themed HTML Pages",
        "",
    ]
    for page in sorted(pages):
        lines.append(f"- `{page.relative_to(OUT).as_posix()}`")
    (OUT / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not ROOT.exists():
        raise SystemExit(f"Missing mirror root: {ROOT}")
    copy_mirror()
    write_assets()

    generated: list[Path] = []
    sources = html_files()
    for source in sources:
        out = output_path_for(source)
        render_page(source, out)
        generated.append(out)

    home_source = ROOT / "WebMjb/mjb.html"
    render_page(home_source, OUT / "index.html", home_index=True)
    generated.append(OUT / "index.html")
    rewrite_text_asset_urls()
    write_manifest(generated)
    print(f"Generated {len(generated)} themed HTML pages in {OUT}")


if __name__ == "__main__":
    main()
