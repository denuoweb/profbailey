#!/usr/bin/env python3
from __future__ import annotations

import posixpath
import re
import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote, unquote, urlsplit

from lxml import html

from build_archive import LOCAL_HOSTS, URL_ATTRS, normalize_local_abs_path


ARCHIVE = Path("archive")
OUT = Path("hosting")
ASSET_BUCKET_URL = "https://storage.googleapis.com/profbailey-archive-assets/"
SMALL_FILE_LIMIT = 256 * 1024

CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
STRING_RE = re.compile(r"(?P<quote>['\"])(?P<value>[^'\"]{1,500})(?P=quote)")
TEXT_LOCAL_URL_RE = re.compile(
    r"https?://(?:web\.engr\.oregonstate\.edu|cs\.oregonstate\.edu|eecs\.oregonstate\.edu)/~mjb/[^\s\"'<>)]*",
    re.I,
)


def rel_posix(path: Path) -> str:
    return path.as_posix()


def archive_rel(path: Path) -> PurePosixPath:
    return PurePosixPath(rel_posix(path.relative_to(ARCHIVE)))


def output_rel(path: Path) -> PurePosixPath:
    return PurePosixPath(rel_posix(path.relative_to(OUT)))


def manifest_pages() -> set[PurePosixPath]:
    manifest = ARCHIVE / "MANIFEST.md"
    pages: set[PurePosixPath] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.match(r"- `(.+)`", line)
        if match:
            pages.add(PurePosixPath(match.group(1)))
    return pages


def hosted_paths(pages: set[PurePosixPath]) -> set[PurePosixPath]:
    hosted = set(pages)
    for path in ARCHIVE.rglob("*"):
        if not path.is_file():
            continue
        rel = archive_rel(path)
        if rel.parts and rel.parts[0] == "assets":
            hosted.add(rel)
        elif path.suffix.lower() in {".css", ".js"}:
            hosted.add(rel)
        elif path.stat().st_size <= SMALL_FILE_LIMIT:
            hosted.add(rel)
    return hosted


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


def harden_external_surface(node: html.HtmlElement) -> None:
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


def bucket_url(rel: PurePosixPath, query: str = "", fragment: str = "") -> str:
    url = ASSET_BUCKET_URL + quote(rel.as_posix(), safe="/")
    if query:
        url += "?" + query
    if fragment:
        url += "#" + fragment
    return url


def resolve_archive_target(value: str, source_rel: PurePosixPath) -> tuple[PurePosixPath, str, str] | None:
    if is_skippable_url(value):
        return None

    parts = urlsplit(value.strip())
    if parts.scheme in {"http", "https"}:
        if parts.netloc.lower() not in LOCAL_HOSTS:
            return None
        target = normalize_local_abs_path(parts)
        if target is None:
            return None
        return target, parts.query, parts.fragment

    if parts.scheme:
        return None

    if parts.path.startswith("/"):
        return None

    source_dir = source_rel.parent
    joined = posixpath.normpath(posixpath.join(source_dir.as_posix(), unquote(parts.path)))
    if joined.startswith("../"):
        return None

    return PurePosixPath(joined), parts.query, parts.fragment


def rewrite_url(value: str, source_rel: PurePosixPath, hosted: set[PurePosixPath]) -> str:
    if "," in value and re.search(r"\s+\d+[wx](?:\s*,|$)", value):
        rewritten_parts = []
        for chunk in value.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            bits = chunk.split()
            bits[0] = rewrite_url(bits[0], source_rel, hosted)
            rewritten_parts.append(" ".join(bits))
        return ", ".join(rewritten_parts)

    resolved = resolve_archive_target(value, source_rel)
    if resolved is None:
        return value

    target, query, fragment = resolved
    if target in hosted:
        return value
    if (ARCHIVE / target.as_posix()).exists():
        return bucket_url(target, query, fragment)
    return value


def rewrite_css_urls(text: str, source_rel: PurePosixPath, hosted: set[PurePosixPath]) -> str:
    def replace(match: re.Match[str]) -> str:
        quote_char = match.group(1)
        value = match.group(2)
        rewritten = rewrite_url(value, source_rel, hosted)
        return f"url({quote_char}{rewritten}{quote_char})"

    return CSS_URL_RE.sub(replace, text)


def rewrite_html_file(path: Path, hosted: set[PurePosixPath]) -> None:
    source_rel = output_rel(path)
    parser = html.HTMLParser(encoding="utf-8")
    document = html.parse(str(path), parser).getroot()

    for node in document.iter():
        if not isinstance(node.tag, str):
            continue
        tag = node.tag.lower()
        harden_external_surface(node)
        for attr in URL_ATTRS.get(tag, ()):
            if attr in node.attrib:
                node.attrib[attr] = rewrite_url(node.attrib[attr], source_rel, hosted)
        if "style" in node.attrib:
            node.attrib["style"] = rewrite_css_urls(node.attrib["style"], source_rel, hosted)
        if tag == "style" and node.text:
            node.text = rewrite_css_urls(node.text, source_rel, hosted)

    rendered = "<!DOCTYPE html>\n" + html.tostring(document, encoding="unicode", method="html")
    path.write_text(rendered, encoding="utf-8")


def rewrite_text_file(path: Path, hosted: set[PurePosixPath]) -> None:
    source_rel = output_rel(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return

    def replace_absolute(match: re.Match[str]) -> str:
        resolved = resolve_archive_target(match.group(0), source_rel)
        if resolved is None:
            return match.group(0)
        target, query, fragment = resolved
        if (ARCHIVE / target.as_posix()).exists():
            return bucket_url(target, query, fragment)
        return match.group(0)

    def replace_string(match: re.Match[str]) -> str:
        quote_char = match.group("quote")
        value = match.group("value")
        if (
            " " in value
            or "\n" in value
            or not ("/" in value or "." in value)
            or value.startswith(("#", ".", "@"))
        ):
            return match.group(0)
        rewritten = rewrite_url(value, source_rel, hosted)
        if rewritten == value:
            return match.group(0)
        return f"{quote_char}{rewritten}{quote_char}"

    rewritten = TEXT_LOCAL_URL_RE.sub(replace_absolute, text)
    if path.suffix.lower() == ".css":
        rewritten = rewrite_css_urls(rewritten, source_rel, hosted)
    elif path.suffix.lower() == ".js":
        rewritten = STRING_RE.sub(replace_string, rewritten)

    if rewritten != text:
        path.write_text(rewritten, encoding="utf-8")


def copy_hosted_files(hosted: set[PurePosixPath]) -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel in sorted(hosted):
        source = ARCHIVE / rel.as_posix()
        if not source.is_file():
            continue
        destination = OUT / rel.as_posix()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    if not ARCHIVE.exists():
        raise SystemExit("Missing archive/. Run tools/build_archive.py first.")

    pages = manifest_pages()
    hosted = hosted_paths(pages)
    copy_hosted_files(hosted)

    for rel in sorted(hosted):
        path = OUT / rel.as_posix()
        if not path.is_file():
            continue
        if rel in pages:
            rewrite_html_file(path, hosted)
        elif path.suffix.lower() in {".css", ".js"}:
            rewrite_text_file(path, hosted)

    total_bytes = sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file())
    print(f"Generated {len(hosted)} Firebase Hosting files in {OUT} ({total_bytes:,} bytes)")
    print(f"Large archive assets resolve to {ASSET_BUCKET_URL}")


if __name__ == "__main__":
    main()
