#!/usr/bin/env python3
import argparse
import subprocess
import re
import sys
from pathlib import Path

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
