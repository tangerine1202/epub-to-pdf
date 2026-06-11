#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pillow>=10.0.0",
# ]
# ///

import argparse
import datetime
import html
import mimetypes
import uuid
import zipfile
import re
from pathlib import Path
from PIL import Image

def natural_sort_key(path: Path) -> list:
    """Sort filenames containing numbers naturally (e.g. p2 before p10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', path.name)]

def main():
    parser = argparse.ArgumentParser(
        description="Convert a directory of images into a fixed-layout EPUB 3."
    )
    parser.add_argument("image_dir", help="Directory containing the images")
    parser.add_argument("-o", "--output", help="Path to the output .epub file")
    parser.add_argument("-t", "--title", help="Title of the book (defaults to directory name)")
    parser.add_argument("-a", "--author", default="Unknown", help="Author of the book")
    parser.add_argument("-l", "--language", default="ja", help="Language code (e.g., 'ja', 'en')")
    parser.add_argument(
        "-d", "--direction",
        choices=["ltr", "rtl"],
        default="rtl",
        help="Page progression direction: 'ltr' or 'rtl' (default: 'rtl' for manga)"
    )

    args = parser.parse_args()

    image_dir = Path(args.image_dir)
    if not image_dir.exists() or not image_dir.is_dir():
        print(f"Error: Directory '{image_dir}' does not exist.")
        return

    # Find and sort images
    supported_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    image_paths = sorted(
        [p for p in image_dir.iterdir() if p.suffix.lower() in supported_extensions],
        key=natural_sort_key
    )

    if not image_paths:
        print(f"Error: No images found in '{image_dir}' with supported extensions: {supported_extensions}")
        return

    print(f"Found {len(image_paths)} images. Processing...")

    # Determine output path
    if args.output:
        output_epub = Path(args.output)
    else:
        # Default to output/ directory in current folder
        output_dir = Path("output")
        output_dir.mkdir(exist_ok=True)
        # Clean up directory name for filename
        safe_name = re.sub(r'[^\w\-_\.]', '_', image_dir.name)
        output_epub = output_dir / f"{safe_name}.epub"

    title = args.title or image_dir.name
    author = args.author
    language = args.language
    direction = args.direction

    # Generate a unique UUID for this book
    book_id = f"urn:uuid:{uuid.uuid4()}"
    modified_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Start writing EPUB ZIP
    print(f"Creating EPUB: {output_epub}")
    with zipfile.ZipFile(output_epub, "w") as z:
        # 1. mimetype (MUST be first and uncompressed)
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""
        z.writestr("META-INF/container.xml", container_xml, compress_type=zipfile.ZIP_DEFLATED)

        # We will accumulate manifest and spine elements
        manifest_items = []
        spine_items = []
        nav_entries = []

        # Add nav document to manifest (but not spine)
        manifest_items.append('    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

        # Add image and xhtml files
        for i, img_path in enumerate(image_paths):
            ext = img_path.suffix
            img_filename = f"page_{i:04d}{ext}"
            xhtml_filename = f"page_{i:04d}.xhtml"

            # Get MIME type
            mime_type, _ = mimetypes.guess_type(img_path.name)
            if not mime_type:
                if ext.lower() in ('.jpg', '.jpeg'):
                    mime_type = 'image/jpeg'
                elif ext.lower() == '.png':
                    mime_type = 'image/png'
                elif ext.lower() == '.webp':
                    mime_type = 'image/webp'
                elif ext.lower() == '.gif':
                    mime_type = 'image/gif'
                else:
                    mime_type = 'application/octet-stream'

            # Get image dimensions using Pillow
            try:
                with Image.open(img_path) as img:
                    width, height = img.size
            except Exception as e:
                print(f"Warning: Could not read dimensions for {img_path.name}: {e}. Using default 1444x2048.")
                width, height = 1444, 2048

            # Write XHTML page
            xhtml_content = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <title>Page {i}</title>
  <meta name="viewport" content="width={width}, height={height}" />
  <style type="text/css">
    body, html {{
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      background-color: #000000;
    }}
    div.page {{
      width: 100%;
      height: 100%;
      display: flex;
      justify-content: center;
      align-items: center;
    }}
    img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
    }}
  </style>
</head>
<body>
  <div class="page">
    <img src="../images/{img_filename}" alt="Page {i}" />
  </div>
</body>
</html>"""
            z.writestr(f"OEBPS/xhtml/{xhtml_filename}", xhtml_content, compress_type=zipfile.ZIP_DEFLATED)

            # Copy image file to zip
            z.write(img_path, f"OEBPS/images/{img_filename}", compress_type=zipfile.ZIP_DEFLATED)

            # Add to manifest
            manifest_items.append(f'    <item id="page_{i:04d}" href="xhtml/{xhtml_filename}" media-type="application/xhtml+xml"/>')
            if i == 0:
                manifest_items.append(f'    <item id="img_{i:04d}" href="images/{img_filename}" media-type="{mime_type}" properties="cover"/>')
            else:
                manifest_items.append(f'    <item id="img_{i:04d}" href="images/{img_filename}" media-type="{mime_type}"/>')

            # Add to spine (explicitly set rendition:layout-pre-paginated so epub2pdf detects it)
            spine_items.append(f'    <itemref idref="page_{i:04d}" properties="rendition:layout-pre-paginated"/>')

            # Accumulate TOC nav entry for the first page
            if i == 0:
                nav_entries.append(f'      <li><a href="xhtml/{xhtml_filename}">Start</a></li>')

        # Write OEBPS/nav.xhtml
        nav_html = f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
  <title>Navigation</title>
</head>
<body>
  <nav epub:type="toc" id="toc">
    <h1>Table of Contents</h1>
    <ol>
{"\n".join(nav_entries)}
    </ol>
  </nav>
</body>
</html>"""
        z.writestr("OEBPS/nav.xhtml", nav_html, compress_type=zipfile.ZIP_DEFLATED)

        # Write OEBPS/content.opf
        manifest_str = "\n".join(manifest_items)
        spine_str = "\n".join(spine_items)

        opf_content = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{html.escape(book_id)}</dc:identifier>
    <dc:title>{html.escape(title)}</dc:title>
    <dc:language>{html.escape(language)}</dc:language>
    <dc:creator>{html.escape(author)}</dc:creator>
    <meta property="dcterms:modified">{modified_time}</meta>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta name="cover" content="img_0000"/>
  </metadata>
  <manifest>
{manifest_str}
  </manifest>
  <spine page-progression-direction="{direction}">
{spine_str}
  </spine>
</package>"""
        z.writestr("OEBPS/content.opf", opf_content, compress_type=zipfile.ZIP_DEFLATED)

    print(f"Successfully created EPUB: {output_epub}")

if __name__ == "__main__":
    main()
