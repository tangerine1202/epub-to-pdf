#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "pyyaml>=6.0.3",
# ]
# ///
import argparse
import subprocess
import re
import sys
from pathlib import Path

# Require PyYAML for metadata parsing. If it's missing, exit with a helpful message.
try:
    import yaml
except Exception:
    print("Error: PyYAML is required for reading metadata.yaml. Install with: pip install pyyaml")
    sys.exit(1)

def load_fontsize_from_metadata(meta_path=Path("metadata.yaml")):
    """Load and normalize the `fontsize` value from metadata.yaml using PyYAML.

    Returns a string with units (e.g. '12pt') or None if not present.
    """
    if not meta_path.exists():
        return None

    text = meta_path.read_text(encoding='utf-8')

    try:
        data = yaml.safe_load(text) or {}
        value = data.get('fontsize')
    except Exception:
        # If YAML parsing fails for any reason, return None and let caller proceed.
        return None

    if value is None:
        return None

    # Normalize numeric values to 'pt'
    if isinstance(value, (int, float)):
        return f"{value}pt"

    v = str(value).strip()
    # remove surrounding quotes if present
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()

    # If it's a bare number, append pt
    if re.fullmatch(r'\d+(?:\.\d+)?', v):
        return f"{v}pt"

    # Otherwise assume the user provided units (e.g. '12pt') and return as-is
    return v

def load_pagesize_from_metadata(meta_path=Path("metadata.yaml")):
    """Load and normalize the `pagesize` value from metadata.yaml using PyYAML.

    Returns a normalized string (e.g. 'a5') or the original value for explicit dimensions.
    """
    if not meta_path.exists():
        return None

    try:
        data = yaml.safe_load(meta_path.read_text(encoding='utf-8')) or {}
    except Exception:
        # If YAML parsing fails for any reason, return None and let caller proceed.
        return None

    value = data.get('pagesize') if isinstance(data, dict) else None
    if value is None:
        return None

    v = str(value).strip()
    # remove surrounding quotes if present
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()

    # Normalize common token forms like 'A5' -> 'a5'
    v_lower = v.lower()
    if re.fullmatch(r'[a-z]\d+', v_lower):
        return v_lower

    # Otherwise return as-is (e.g. explicit dimensions like '105mmx148mm')
    return v

def load_layout_from_metadata(meta_path=Path("metadata.yaml")):
    """Load pagesize, margin, and columns from metadata.yaml using PyYAML.

    Returns a tuple (pagesize, margin_dict, columns) where:
      - pagesize is a normalized token like 'a5' or the raw string provided
      - margin_dict is a dict that may contain 'x' and/or 'y' margin strings
      - columns is an integer number of columns (or None)
    """
    if not meta_path.exists():
        return (None, {}, None)

    try:
        data = yaml.safe_load(meta_path.read_text(encoding='utf-8')) or {}
    except Exception:
        # If YAML parsing fails for any reason, return safe defaults
        return (None, {}, None)

    pagesize = None
    margin = {}
    columns = None

    if isinstance(data, dict):
        pagesize = data.get('pagesize') or data.get('page-size') or data.get('paper')
        # Accept either a mapping under 'margin' or scalar values
        raw_margin = data.get('margin') or {}
        columns = data.get('columns') or data.get('page_columns') or data.get('page-columns')

        # Normalize margin into a dict with optional 'x' and 'y' keys
        if isinstance(raw_margin, dict):
            mx = raw_margin.get('x') or raw_margin.get('horizontal') or raw_margin.get('left') or raw_margin.get('right')
            my = raw_margin.get('y') or raw_margin.get('vertical') or raw_margin.get('top') or raw_margin.get('bottom')
            if mx is not None:
                margin['x'] = str(mx)
            if my is not None:
                margin['y'] = str(my)
        else:
            # If margin is a scalar (e.g. "1.0cm"), apply it to both axes
            if raw_margin:
                margin['x'] = str(raw_margin)
                margin['y'] = str(raw_margin)

    if pagesize is not None:
        pagesize = str(pagesize).strip().lower()

    # Normalize columns to integer when possible
    if columns is not None:
        try:
            columns = int(columns)
        except Exception:
            columns = None

    return (pagesize, margin, columns)

def rebuild(epub_path, output_dir):
    # Use Path from pathlib
    epub_file = Path(epub_path)
    output_path = Path(output_dir)

    # 1. Validate input exists
    if not epub_file.exists():
        print(f"Error: {epub_file} not found.")
        sys.exit(1)

    # 2. Check input file extension
    if epub_file.suffix.lower() != '.epub':
        print(f"Error: Choice {epub_file.suffix} is not a valid EPUB file.")
        sys.exit(1)

    # Extract basename without extension (stem)
    base_name = epub_file.stem

    # Ensure output directory exists (parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)

    typ_path = output_path / f"{base_name}.typ"
    pdf_path = output_path / f"{base_name}.pdf"

    # 3. Pandoc conversion
    print(f"Generating {typ_path} from {epub_file}...")
    try:
        subprocess.run([
            "pandoc", str(epub_file),
            "--metadata-file=metadata.yaml",
            "-o", str(typ_path),
            "--standalone"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during Pandoc conversion: {e}")
        sys.exit(1)

    # 4. Post-processing (Cleanups)
    print(f"Post-processing {typ_path}...")
    content = typ_path.read_text(encoding='utf-8')

    # 4.1 Remove lines that only contain <*.xhtml>
    # Note: re.MULTILINE flag to ensure ^ matches start of line
    content = re.sub(r'^<.*\.xhtml>\s*$', '', content, flags=re.MULTILINE)

    # 4.2 Remove references to missing images to prevent Typst compilation failure
    def remove_missing_image(match):
        img_path_str = match.group('path')
        # Image paths in .typ are relative to the .typ file's location (output_path)
        if not (output_path / img_path_str).exists():
            print(f"  Note: Missing image '{img_path_str}' reference removed.")
            return ""
        return match.group(0)

    # Match #box(image("...")) or image("...")
    content = re.sub(r'#box\(image\("(?P<path>[^"]+)"\)\)\s*', remove_missing_image, content)
    content = re.sub(r'image\("(?P<path>[^"]+)"\)', remove_missing_image, content)

    # 4.3 Remove links to missing labels to prevent Typst compilation failure
    # A label is "defined" if it appears in the text as <label> but NOT as part of a reference like #link(<label>)
    all_label_instances = re.findall(r'<([a-zA-Z0-9_:.#-]+)>', content)
    link_instances = re.findall(r'#link\(<([a-zA-Z0-9_:.#-]+)>\)', content)

    # Count occurrences
    instance_counts = {}
    for l in all_label_instances:
        instance_counts[l] = instance_counts.get(l, 0) + 1

    link_counts = {}
    for l in link_instances:
        link_counts[l] = link_counts.get(l, 0) + 1

    # A label is defined if it has more total <label> instances than #link(<label>) instances
    defined_labels = {l for l, count in instance_counts.items() if count > link_counts.get(l, 0)}

    def remove_missing_link(match):
        label = match.group(1)
        text = match.group(2)
        if label not in defined_labels:
            print(f"  Note: Missing label '<{label}>' link for '{text}' removed.")
            return text # Keep only the text, remove the #link(...) part
        return match.group(0)

    # Match #link(<label_name>)[link_text]
    content = re.sub(r'#link\(<([a-zA-Z0-9_:.#-]+)>\)\[([^\]]+)\]', remove_missing_link, content)

    # Load pagesize, margin, and columns from metadata.yaml using the top-level utility function.
    pagesize, margin_cfg, page_columns = load_layout_from_metadata(Path('metadata.yaml'))
    # Default pagesize to 'a5' when not specified
    pagesize = (pagesize or 'a5')
    if isinstance(pagesize, str):
        pagesize = pagesize.strip().lower()

    # Normalize margin values (prefer explicit per-axis values, fallback to a sensible default)
    margin_x = None
    margin_y = None
    if isinstance(margin_cfg, dict):
        margin_x = margin_cfg.get('x')
        margin_y = margin_cfg.get('y')

    # Choose a default margin if none provided
    if not margin_x and not margin_y:
        margin_x = '1.0cm'
        margin_y = '1.0cm'

    # Determine columns (default to 1)
    cols = page_columns if (isinstance(page_columns, int) and page_columns > 0) else 1

    # Only prepend a page directive when there isn't already a page/paper directive
    if not re.search(r'(?m)^#set\s+page\s*\(', content) and not re.search(r'(?m)^#set\s+(paper|page-size)\s*:', content):
        # Format margin for Typst: use a tuple-like appearance for the margin parameter
        # (the exact format is passed as a string to the directive as requested)
        margin_repr = f'(x: {margin_x}, y: {margin_y})' if margin_x and margin_y else (margin_x or margin_y)
        page_directive = f'#set page(paper: "{pagesize}", margin: {margin_repr}, columns: {cols})\n\n'
        content = page_directive + content
        print(f'  Applied page directive from metadata.yaml: paper={pagesize}, margin={margin_repr}, columns={cols}')

    # Load fontsize from metadata.yaml using the top-level utility function.
    fontsize = load_fontsize_from_metadata(Path('metadata.yaml'))
    if fontsize:
        fs = fontsize  # already normalized to include units (e.g. '12pt')
        # Only prepend if there's not already a fontsize directive in the content
        if not re.search(r'(?m)^#set\s+fontsize\s*:', content):
            directive = f'#set fontsize: {fs}\n\n'
            content = directive + content
            print(f"  Applied fontsize from metadata.yaml: {fs}")

    typ_path.write_text(content, encoding='utf-8')

    # 5. Typst compilation
    print(f"Compiling {pdf_path}...")
    try:
        subprocess.run([
            "typst", "compile", str(typ_path),
            "--font-path", "/Users/alan/Library/Fonts"
        ], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during Typst compilation: {e}")
        sys.exit(1)

    print(f"Done! {pdf_path} has been generated successfully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild Typst files from EPUB with metadata settings.")
    parser.add_argument("epub_path", help="Path to the input .epub file")
    parser.add_argument("--out", default="books", help="Output directory (default: books)")

    args = parser.parse_args()

    rebuild(args.epub_path, args.out)
