#!/usr/bin/env python3
from __future__ import annotations

import html as html_escape
import json
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
WEBGL_SAMPLE = PurePosixPath("webgl/sample.html")

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


def is_blank_target(value: str) -> bool:
    return value.strip().strip("\"'").lower() == "_blank"


def harden_external_surface(node: etree._Element) -> None:
    tag = node.tag.lower()
    if tag == "a" and is_blank_target(node.attrib.get("target", "")):
        rel_tokens = set(node.attrib.get("rel", "").split())
        rel_tokens.update({"noopener", "noreferrer"})
        node.attrib["rel"] = " ".join(sorted(rel_tokens))
    elif tag == "iframe":
        if "loading" not in node.attrib:
            node.attrib["loading"] = "lazy"
        if "referrerpolicy" not in node.attrib:
            node.attrib["referrerpolicy"] = "strict-origin-when-cross-origin"
        if "sandbox" not in node.attrib:
            node.attrib["sandbox"] = "allow-scripts allow-same-origin allow-presentation allow-popups"


def externalize_webgl_sample_scripts(body: etree._Element, source_path: Path, output_path: Path) -> None:
    if root_relative(source_path) != WEBGL_SAMPLE:
        return

    for script in list(body.iter("script")):
        if "src" not in script.attrib:
            script.drop_tree()

    first_script = body.find(".//script[@src]")
    helper_scripts = ("sample-shaders.js", "sample-ui.js")
    new_nodes = []
    for name in helper_scripts:
        node = etree.Element("script")
        node.attrib["src"] = to_archive_rel(PurePosixPath("webgl") / name, output_path)
        new_nodes.append(node)

    if first_script is None:
        body.extend(new_nodes)
        return

    parent = first_script.getparent()
    if parent is None:
        body.extend(new_nodes)
        return

    index = parent.index(first_script)
    for node in new_nodes:
        parent.insert(index, node)
        index += 1


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

        harden_external_surface(node)

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

    externalize_webgl_sample_scripts(body, source_path, output_path)


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


def course_label(slug: str | None) -> str:
    for course_slug, label, _ in COURSES:
        if course_slug == slug:
            return label
    return "Archive"


def segment_label(segment: str) -> str:
    decoded = unquote(segment)
    stem = re.sub(r"\.html?$", "", decoded, flags=re.I)
    for slug, label, _ in COURSES:
        if stem == slug:
            return label
    match = re.fullmatch(r"cs(\d+)(v?)", stem, flags=re.I)
    if match:
        return f"CS {match.group(1)}{match.group(2)}"
    words = re.sub(r"[_-]+", " ", stem)
    words = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", words)
    return words[:1].upper() + words[1:]


def directory_index_target(path: PurePosixPath) -> PurePosixPath | None:
    if path.as_posix() == ".":
        return PurePosixPath("index.html")
    if path.as_posix() == "WebMjb":
        target = PurePosixPath("WebMjb/mjb.html")
        if (ROOT / target.as_posix()).is_file():
            return target
    if len(path.parts) == 1 and path.parts[0] in {course for course, _, _ in COURSES}:
        return path / "index.html"
    for index_name in ("index.html", "index.htm"):
        target = path / index_name
        source = ROOT / target.as_posix()
        if source.is_file() and looks_like_html(source):
            return target
    return None


def breadcrumb_items(source_path: Path, output_path: Path, title: str, *, home_index: bool = False) -> list[str]:
    home_href = to_archive_rel(PurePosixPath("index.html"), output_path)
    if home_index:
        return ['<li aria-current="page"><span>Home</span></li>']

    rel = root_relative(source_path)
    parts = list(rel.parts)
    if not parts:
        return [f'<li><a href="{html_escape.escape(home_href)}">Home</a></li>']

    rendered = [f'<li><a href="{html_escape.escape(home_href)}">Home</a></li>']
    current_is_index = parts[-1].lower() in {"index.html", "index.htm"}
    dirs = parts[:-1] if current_is_index else parts[:-1]

    cumulative_parts: list[str] = []
    for index, part in enumerate(dirs):
        cumulative_parts.append(part)
        cumulative = PurePosixPath(*cumulative_parts)
        label = segment_label(part)
        is_current_dir = current_is_index and index == len(dirs) - 1

        if is_current_dir:
            rendered.append(f'<li aria-current="page"><span>{html_escape.escape(label)}</span></li>')
            continue

        target = directory_index_target(cumulative)
        if target == rel:
            continue
        if target is not None:
            href = to_archive_rel(target, output_path)
            rendered.append(f'<li><a href="{html_escape.escape(href)}">{html_escape.escape(label)}</a></li>')
        else:
            rendered.append(f'<li><span>{html_escape.escape(label)}</span></li>')

    if not current_is_index:
        current_label = title or segment_label(parts[-1])
        rendered.append(f'<li aria-current="page"><span>{html_escape.escape(current_label)}</span></li>')

    return rendered


def archive_breadcrumb(source_path: Path, output_path: Path, title: str, *, home_index: bool = False) -> str:
    return "\n          ".join(breadcrumb_items(source_path, output_path, title, home_index=home_index))


def course_menu(output_path: Path, current_course: str | None = None) -> str:
    rendered = []
    for slug, label, description in COURSES:
        href = to_archive_rel(PurePosixPath(slug) / "index.html", output_path)
        aria = ' aria-current="page"' if current_course == slug else ""
        rendered.append(
            f"""
            <a href="{html_escape.escape(href)}"{aria}>
              <span>{html_escape.escape(label)}</span>
              <small>{html_escape.escape(description)}</small>
            </a>
            """.strip()
        )
    return "\n          ".join(rendered)


def archive_topbar(
    source_path: Path,
    output_path: Path,
    title: str,
    current_course: str | None = None,
    current_home: bool = False,
) -> str:
    home_href = to_archive_rel(PurePosixPath("index.html"), output_path)
    return f"""
    <header class="archive-topbar">
      <div class="archive-brand-block">
        <a class="archive-brand" href="{html_escape.escape(home_href)}">Bailey Archive</a>
        <nav class="archive-breadcrumb" aria-label="Breadcrumb">
          <ol>
            {archive_breadcrumb(source_path, output_path, title, home_index=current_home)}
          </ol>
        </nav>
      </div>
      <nav class="archive-actions" aria-label="Archive navigation">
        <details class="archive-menu course-menu" name="archive-menu">
          <summary>Courses</summary>
          <div class="archive-menu-panel course-menu-panel">
            {course_menu(output_path, current_course=current_course)}
          </div>
        </details>
        <details class="archive-menu theme-menu" name="archive-menu">
          <summary>Theme</summary>
          <div class="archive-menu-panel theme-menu-panel" data-theme-controls role="group" aria-label="Theme switcher">
            <button type="button" data-theme="system" aria-pressed="true">System</button>
            <button type="button" data-theme="light" aria-pressed="false">Light</button>
            <button type="button" data-theme="dark" aria-pressed="false">Dark</button>
            <button type="button" data-theme="cyber" aria-pressed="false">Cyber</button>
          </div>
        </details>
      </nav>
    </header>
    """


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
<html lang="en" data-theme-preference="system" data-theme-storage-key="{THEME_STORAGE_KEY}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Mirrored offsite archive of {escaped_title}.">
  <meta name="robots" content="noindex,nofollow,noarchive">
  <title>{escaped_title} | Bailey Mirrored Offsite Archive</title>
  <link rel="stylesheet" href="{rel_asset(output_path, "theme-tokens.css")}">
  <link rel="stylesheet" href="{rel_asset(output_path, "archive.css")}">
  <script type="module" src="{rel_asset(output_path, "theme-toggle.js")}"></script>
</head>
<body>
  <main class="showcase archive-page" id="main-content">
    {archive_topbar(source_path, output_path, title, current_course=current_course, current_home=home)}

    {intro}

    <section class="showcase-section legacy-content" id="archived-content" aria-label="Archived page content">
{content}
    </section>

    <footer class="archive-footer">
      <p class="eyebrow">Mirrored Offsite Archive</p>
      <p>
        Archived from <a href="{escaped_source_note}" target="_blank" rel="noopener noreferrer">{escaped_source_note}</a> on {ARCHIVE_DATE}.
        Project source: <a href="{escaped_github_url}" target="_blank" rel="noopener noreferrer">GitHub</a>.
      </p>
    </footer>
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

.eyebrow {
  margin: 0 0 0.35rem;
  color: var(--text-muted);
  font-size: 0.85rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.archive-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 1rem;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 0.75rem;
  background: var(--surface-1);
  box-shadow: var(--shadow-soft);
}

.archive-topbar,
.archive-topbar *,
.archive-topbar *::before,
.archive-topbar *::after {
  box-sizing: border-box;
}

.archive-brand-block {
  min-width: 0;
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 0.65rem;
}

.archive-brand {
  flex: 0 0 auto;
  color: var(--text-color);
  font-weight: 800;
  text-decoration: none;
}

.archive-breadcrumb {
  min-width: 0;
  flex: 1 1 auto;
  padding-left: 0.65rem;
  border-left: 1px solid var(--border-color);
  color: var(--text-muted);
}

.archive-breadcrumb ol {
  min-width: 0;
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0;
  list-style: none;
}

.archive-breadcrumb li {
  min-width: 0;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
}

.archive-breadcrumb li[aria-current="page"] {
  flex: 1 1 auto;
}

.archive-breadcrumb li + li::before {
  margin: 0 0.45rem;
  color: var(--text-muted);
  content: "/";
}

.archive-breadcrumb a,
.archive-breadcrumb span {
  min-width: 0;
  color: var(--text-muted);
  font-size: 0.95rem;
  font-weight: 700;
  line-height: 1.25;
  text-decoration: none;
  white-space: nowrap;
}

.archive-breadcrumb a:hover,
.archive-breadcrumb a:focus-visible {
  color: var(--accent-color);
}

.archive-breadcrumb li[aria-current="page"] span {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}

.archive-actions {
  min-width: 0;
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.archive-menu > summary {
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  padding: 0.45rem 0.75rem;
  border: 1px solid var(--border-color);
  border-radius: 0.625rem;
  background: var(--surface-2);
  color: var(--text-color);
  font-weight: 700;
  line-height: 1;
  text-decoration: none;
}

.archive-menu[open] > summary {
  border-color: var(--accent-color);
  color: var(--accent-color);
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

.archive-menu {
  position: relative;
}

.archive-menu > summary {
  cursor: pointer;
  list-style: none;
}

.archive-menu > summary::-webkit-details-marker {
  display: none;
}

.archive-menu > summary::after {
  width: 0.42rem;
  height: 0.42rem;
  border-right: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  content: "";
  transform: rotate(45deg) translateY(-0.1rem);
}

.archive-menu[open] > summary::after {
  transform: rotate(225deg) translate(-0.05rem, -0.05rem);
}

.archive-menu-panel {
  position: absolute;
  top: calc(100% + 0.4rem);
  right: 0;
  z-index: 10;
  width: min(22rem, calc(100vw - 2rem));
  padding: 0.5rem;
  border: 1px solid var(--border-color);
  border-radius: 0.75rem;
  background: var(--surface-1);
  box-shadow: var(--shadow-strong);
}

.course-menu-panel {
  display: grid;
  gap: 0.35rem;
  max-height: min(32rem, calc(100vh - 8rem));
  overflow-y: auto;
}

.course-menu-panel a {
  min-height: 44px;
  display: grid;
  gap: 0.12rem;
  padding: 0.55rem 0.7rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  color: var(--text-color);
  text-decoration: none;
}

.course-menu-panel a:hover,
.course-menu-panel a:focus-visible,
.theme-menu-panel button:hover,
.theme-menu-panel button:focus-visible {
  border-color: var(--accent-color);
  color: var(--accent-color);
}

.course-menu-panel a[aria-current="page"],
.theme-menu-panel button[aria-pressed="true"] {
  border-color: var(--accent-color);
  color: var(--accent-color);
  box-shadow: inset 0 0 0 1px var(--border-strong);
}

.course-menu-panel small {
  color: var(--text-muted);
  font-size: 0.85rem;
  line-height: 1.2;
}

.theme-menu-panel {
  display: grid;
  gap: 0.35rem;
  width: min(12rem, calc(100vw - 2rem));
}

.theme-menu-panel button {
  min-height: 44px;
  padding: 0.55rem 0.7rem;
  border: 1px solid transparent;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--text-color);
  font: 700 0.95rem/1 var(--font-body);
  text-align: left;
  cursor: pointer;
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

.archive-footer {
  margin-top: 1rem;
  padding: 0.9rem 1rem;
  border-top: 1px solid var(--border-color);
  color: var(--text-muted);
  font-size: 0.95rem;
}

.archive-footer p {
  margin: 0;
}

.archive-footer p + p {
  margin-top: 0.35rem;
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

.legacy-webgl-slider {
  width: min(26rem, 100%);
}

@media (max-width: 900px) {
  .course-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .archive-topbar {
    align-items: stretch;
    flex-direction: column;
    gap: 0.55rem;
    padding: 0.55rem;
  }

  .archive-brand-block,
  .archive-actions {
    width: 100%;
  }

  .archive-brand-block {
    flex-wrap: wrap;
  }

  .archive-breadcrumb {
    flex-basis: 100%;
    padding-top: 0.15rem;
    padding-left: 0;
    border-left: 0;
  }

  .archive-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.4rem;
  }

  .archive-menu {
    min-width: 0;
    width: 100%;
  }

  .archive-menu[open] {
    grid-column: 1 / -1;
  }

  .archive-menu > summary {
    min-width: 0;
    width: 100%;
    padding-right: 0.55rem;
    padding-left: 0.55rem;
  }

  .archive-menu > summary::after {
    flex: 0 0 auto;
  }

  .archive-menu-panel {
    position: static;
    width: 100%;
    margin-top: 0.4rem;
  }

  .course-menu-panel {
    max-height: none;
  }

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

@media (max-width: 520px) {
  .archive-actions {
    grid-template-columns: 1fr;
  }

  .archive-breadcrumb li:not(:first-child):not([aria-current="page"]) {
    display: none;
  }

  .archive-breadcrumb li + li::before {
    margin-right: 0.35rem;
    margin-left: 0.35rem;
  }
}
"""
    (ASSETS / "archive.css").write_text(archive_css, encoding="utf-8")


def write_webgl_helpers() -> None:
    sample_source = ROOT / WEBGL_SAMPLE.as_posix()
    if not sample_source.exists():
        return

    parser = html.HTMLParser(encoding="utf-8")
    document = html.parse(str(sample_source), parser).getroot()
    shaders = {}
    for shader_id in ("vertex-shader", "fragment-shader"):
        node = document.find(f".//script[@id='{shader_id}']")
        if node is not None and node.text:
            shaders[shader_id] = {
                "type": node.attrib.get("type", "text/plain"),
                "source": node.text,
            }

    webgl_dir = OUT / "webgl"
    webgl_dir.mkdir(parents=True, exist_ok=True)
    (webgl_dir / "sample-shaders.js").write_text(
        f"""(() => {{
  const shaders = {json.dumps(shaders, indent=2)};
  Object.entries(shaders).forEach(([id, shader]) => {{
    if (document.getElementById(id)) {{
      return;
    }}
    const node = document.createElement("script");
    node.id = id;
    node.type = shader.type;
    node.textContent = shader.source;
    document.head.append(node);
  }});
}})();
""",
        encoding="utf-8",
    )
    (webgl_dir / "sample-ui.js").write_text(
        """(() => {
  const defaults = {
    min: 0.1,
    max: 2.0,
    value: 1.0,
    step: 0.01,
    orientation: "horizontal",
  };
  const stateByElement = new WeakMap();

  const ensureSlider = (element) => {
    let state = stateByElement.get(element);
    if (state) {
      return state;
    }

    const input = document.createElement("input");
    input.type = "range";
    input.className = "legacy-webgl-slider";
    input.min = String(defaults.min);
    input.max = String(defaults.max);
    input.step = String(defaults.step);
    input.value = String(defaults.value);
    element.replaceChildren(input);

    state = {
      input,
      options: { ...defaults },
    };
    stateByElement.set(element, state);
    return state;
  };

  const apiFor = (element) => ({
    slider(command, key, value) {
      const state = ensureSlider(element);

      if (command === "value") {
        return Number(state.input.value);
      }

      if (command === "enable") {
        state.input.disabled = false;
        return this;
      }

      if (command === "option") {
        state.options[key] = value;
        if (key === "min" || key === "max" || key === "step" || key === "value") {
          state.input[key] = String(value);
        }
        return this;
      }

      return this;
    },
  });

  window.$ = window.$ || ((selector) => {
    const element = typeof selector === "string" ? document.querySelector(selector) : selector;
    if (!element) {
      return { slider: () => undefined };
    }
    return apiFor(element);
  });

  const slider = window.$("#slider");
  slider.slider();
  slider.slider("option", "min", defaults.min);
  slider.slider("option", "max", defaults.max);
  slider.slider("option", "value", defaults.value);
  slider.slider("option", "step", defaults.step);
  slider.slider("option", "orientation", defaults.orientation);
  slider.slider("enable");
})();
""",
        encoding="utf-8",
    )


def write_robots() -> None:
    (OUT / "robots.txt").write_text(
        "User-agent: *\nDisallow: /\n",
        encoding="utf-8",
    )


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
    write_webgl_helpers()
    write_robots()

    generated: list[Path] = []
    sources = [
        source
        for source in html_files()
        if root_relative(source) != PurePosixPath("index.html")
    ]
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
