#!/usr/bin/env python3
import argparse
import html
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def html_to_markdownish(text: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", "", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", "", text)

    # Headings
    for i in range(1, 7):
        text = re.sub(
            rf"(?is)<h{i}[^>]*>(.*?)</h{i}>",
            lambda m: "\n\n" + ("#" * i) + " " + clean_inline(m.group(1)) + "\n\n",
            text,
        )

    # Paragraphs and line breaks
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p\s*>", "\n\n", text)
    text = re.sub(r"(?is)<p[^>]*>", "", text)

    # Lists
    text = re.sub(r"(?is)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?is)</li>", "", text)

    # Remove remaining tags
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = html.unescape(text)

    # Normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_inline(s: str) -> str:
    s = re.sub(r"(?is)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def find_opf_path(z: zipfile.ZipFile) -> str:
    container_xml = z.read("META-INF/container.xml")
    root = ET.fromstring(container_xml)
    for elem in root.iter():
        if strip_ns(elem.tag) == "rootfile":
            path = elem.attrib.get("full-path")
            if path:
                return path
    raise RuntimeError("Could not find OPF package file in EPUB")


def extract_spine_items(z: zipfile.ZipFile, opf_path: str):
    opf_dir = os.path.dirname(opf_path)
    root = ET.fromstring(z.read(opf_path))

    manifest = {}
    spine_ids = []

    for elem in root.iter():
        name = strip_ns(elem.tag)
        if name == "item":
            item_id = elem.attrib.get("id")
            href = elem.attrib.get("href")
            media_type = elem.attrib.get("media-type", "")
            if item_id and href:
                full = str(Path(opf_dir) / href) if opf_dir else href
                manifest[item_id] = {"href": full, "media_type": media_type}
        elif name == "itemref":
            idref = elem.attrib.get("idref")
            if idref:
                spine_ids.append(idref)

    docs = []
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if not item:
            continue
        mt = item["media_type"]
        href = item["href"]
        if mt in ("application/xhtml+xml", "text/html") or href.lower().endswith((".xhtml", ".html", ".htm")):
            docs.append(href)
    return docs


def convert(epub_path: Path, out_path: Path):
    with zipfile.ZipFile(epub_path, "r") as z:
        opf_path = find_opf_path(z)
        docs = extract_spine_items(z, opf_path)

        chunks = []
        for i, doc in enumerate(docs, start=1):
            try:
                raw = z.read(doc).decode("utf-8", errors="replace")
            except KeyError:
                continue
            md = html_to_markdownish(raw)
            if md:
                chunks.append(f"\n\n<!-- source-section: {doc} -->\n\n{md}\n")

    title = epub_path.stem
    content = f"# {title}\n\n"
    content += f"> Extracted from `{epub_path.name}` for Hermes LLM Wiki ingestion.\n\n"
    content += "\n\n---\n\n".join(chunks)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return len(chunks)


def main():
    parser = argparse.ArgumentParser(description="Convert EPUB to markdown-ish text for LLM Wiki ingestion.")
    parser.add_argument("epub", help="Input EPUB path")
    parser.add_argument("output", help="Output Markdown path")
    args = parser.parse_args()

    epub_path = Path(args.epub)
    out_path = Path(args.output)

    if not epub_path.exists():
        print(f"ERROR: EPUB not found: {epub_path}", file=sys.stderr)
        sys.exit(1)

    count = convert(epub_path, out_path)
    print(f"Converted {count} sections")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()

