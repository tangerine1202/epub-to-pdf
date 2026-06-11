#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pyyaml>=6.0",
# ]
# ///

import argparse
import shutil
import subprocess
import re
import sys
import zipfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from pathlib import PurePosixPath
from typing import Optional, Dict, Tuple, Any, List

# Load PyYAML. If it's missing, exit with a helpful message.
try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Please run this script with 'uv run' to automatically manage dependencies.")
    sys.exit(1)


def normalize_zip_path(base_dir: str, rel_path: str) -> str:
    """Normalize a zip path relative to base_dir, resolving '..' and '.'."""
    combined = PurePosixPath(base_dir) / rel_path
    parts: List[str] = []
    for part in combined.parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def find_tag(element: ET.Element, tag_name: str, ns: Dict[str, str]) -> Optional[ET.Element]:
    """Find a tag inside an XML element, handling namespaces robustly."""
    for prefix in [f"opf:{tag_name}", f"{{http://www.idpf.org/2007/opf}}{tag_name}", tag_name]:
        res = element.find(prefix, ns)
        if res is not None:
            return res
    # Deep search
    for prefix in [f".//opf:{tag_name}", f".//{{http://www.idpf.org/2007/opf}}{tag_name}", f".//{tag_name}"]:
        res = element.find(prefix, ns)
        if res is not None:
            return res
    return None


def find_all_tags(element: ET.Element, tag_name: str, ns: Dict[str, str]) -> List[ET.Element]:
    """Find all occurrences of a tag inside an XML element."""
    for prefix in [f"opf:{tag_name}", f"{{http://www.idpf.org/2007/opf}}{tag_name}", tag_name]:
        res = element.findall(prefix, ns)
        if res:
            return res
    for prefix in [f".//opf:{tag_name}", f".//{{http://www.idpf.org/2007/opf}}{tag_name}", f".//{tag_name}"]:
        res = element.findall(prefix, ns)
        if res:
            return res
    return []


def detect_layout(epub_path: Path) -> str:
    """Detect if the EPUB is fixed-layout ('fixed') or reflowable ('reflow')."""
    try:
        with zipfile.ZipFile(epub_path, "r") as z:
            # 1. Read container.xml to locate OPF file
            container_path = "META-INF/container.xml"
            if container_path not in z.namelist():
                # Fallback to searching for .opf
                opf_candidates = [n for n in z.namelist() if n.endswith(".opf")]
                if not opf_candidates:
                    return "reflow"
                opf_path = opf_candidates[0]
            else:
                container_data = z.read(container_path)
                root = ET.fromstring(container_data)
                ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
                rootfile = root.find(".//c:rootfile", ns)
                if rootfile is not None:
                    opf_path = rootfile.attrib.get("full-path", "")
                else:
                    opf_candidates = [n for n in z.namelist() if n.endswith(".opf")]
                    if not opf_candidates:
                        return "reflow"
                    opf_path = opf_candidates[0]

            if opf_path not in z.namelist():
                return "reflow"

            opf_data = z.read(opf_path)
            root = ET.fromstring(opf_data)
            ns = {"opf": "http://www.idpf.org/2007/opf"}

            # 2. Check metadata rendition:layout
            metadata = find_tag(root, "metadata", ns)
            if metadata is not None:
                for meta in find_all_tags(metadata, "meta", ns):
                    if meta.attrib.get("property") == "rendition:layout" and meta.text == "pre-paginated":
                        return "fixed"
                    if meta.attrib.get("name") == "rendition:layout" and meta.attrib.get("content") == "pre-paginated":
                        return "fixed"

            # 3. Check spine itemref properties
            spine = find_tag(root, "spine", ns)
            if spine is not None:
                for itemref in find_all_tags(spine, "itemref", ns):
                    properties = itemref.attrib.get("properties", "")
                    if "rendition:layout-pre-paginated" in properties:
                        return "fixed"

            # 4. Fallback Heuristics: Check first 5 spine items
            manifest = find_tag(root, "manifest", ns)
            if manifest is not None and spine is not None:
                manifest_map = {item.attrib.get("id"): item.attrib.get("href") for item in find_all_tags(manifest, "item", ns)}
                itemrefs = [itemref.attrib.get("idref") for itemref in find_all_tags(spine, "itemref", ns)]
                
                opf_dir = str(Path(opf_path).parent) if opf_path else ""
                
                image_dominant_pages = 0
                total_pages_checked = 0
                
                for idref in itemrefs[:5]:
                    href = manifest_map.get(idref)
                    if not href:
                        continue
                    xhtml_path = normalize_zip_path(opf_dir, href)
                    if xhtml_path in z.namelist():
                        total_pages_checked += 1
                        try:
                            content = z.read(xhtml_path).decode("utf-8", errors="ignore")
                            # Check if the page is mostly images or SVG
                            text_content = re.sub(r"<[^>]+>", "", content).strip()
                            has_images = bool(re.search(r"<image|<img|<svg", content, re.IGNORECASE))
                            if len(text_content) < 150 and has_images:
                                image_dominant_pages += 1
                        except Exception:
                            pass
                
                if total_pages_checked > 0 and image_dominant_pages / total_pages_checked >= 0.8:
                    return "fixed"

    except Exception as e:
        print(f"Warning during auto-detection: {e}. Defaulting to reflow.")
        
    return "reflow"


def check_dependencies(needs_pandoc: bool) -> bool:
    """Check if the required external CLI programs are installed."""
    missing = []
    if not shutil.which("typst"):
        missing.append("typst (https://typst.app/)")
    if needs_pandoc and not shutil.which("pandoc"):
        missing.append("pandoc (https://pandoc.org/)")
        
    if missing:
        print("Error: Missing required system dependencies:")
        for m in missing:
            print(f"  - {m}")
        print("\nPlease install these tools and make sure they are in your PATH.")
        return False
    return True


def get_default_font_path() -> Optional[Path]:
    """Return default font path on macOS if it exists, otherwise None."""
    if sys.platform == "darwin":
        path = Path.home() / "Library" / "Fonts"
        if path.exists():
            return path
    return None


def parse_cli_margin(margin_str: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse margin string from CLI, e.g., '1.5cm' or 'x:1.0cm,y:1.5cm'."""
    margin_str = margin_str.strip()
    if "," in margin_str or ":" in margin_str:
        margin_x = None
        margin_y = None
        parts = margin_str.split(",")
        for part in parts:
            if ":" in part:
                k, v = part.split(":", 1)
                k = k.strip().lower()
                v = v.strip()
                if k in ["x", "horizontal", "left", "right"]:
                    margin_x = v
                elif k in ["y", "vertical", "top", "bottom"]:
                    margin_y = v
        return margin_x, margin_y
    else:
        return margin_str, margin_str


def load_config(config_path: Optional[Path] = None, layout: Optional[str] = None) -> Dict[str, Any]:
    """Load config from a YAML file, returning a normalized config dict."""
    config = {
        "pagesize": None,
        "fontsize": None,
        "margin": {},
        "columns": None,
        "mainfont": None,
    }
    
    # Locate configuration file if not provided
    if not config_path:
        search_names = []
        if layout == "reflow":
            search_names = ["reflow-config.yaml", "metadata.yaml", "epub2pdf.yaml"]
        elif layout == "fixed":
            search_names = ["fixed-config.yaml", "metadata.yaml", "epub2pdf.yaml"]
        else:
            search_names = ["metadata.yaml", "epub2pdf.yaml"]

        for name in search_names:
            p = Path(name)
            if p.exists():
                config_path = p
                break
                
    if not config_path or not config_path.exists():
        return config

    try:
        # Load all documents from the YAML stream (handles frontmatter '---' wrappers)
        docs = list(yaml.safe_load_all(config_path.read_text(encoding="utf-8")))
        data = {}
        for doc in docs:
            if isinstance(doc, dict) and doc:
                data = doc
                break
    except Exception as e:
        print(f"Warning: Failed to parse config file '{config_path}': {e}. Using defaults.")
        return config

    # 1. Page size
    pagesize = data.get("pagesize") or data.get("page-size") or data.get("paper")
    if pagesize:
        config["pagesize"] = str(pagesize).strip().lower()

    # 2. Font size
    fontsize = data.get("fontsize") or data.get("font-size")
    if fontsize:
        if isinstance(fontsize, (int, float)):
            config["fontsize"] = f"{fontsize}pt"
        else:
            v = str(fontsize).strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1].strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", v):
                config["fontsize"] = f"{v}pt"
            else:
                config["fontsize"] = v

    # 3. Font family
    mainfont = data.get("mainfont") or data.get("font")
    if mainfont:
        config["mainfont"] = str(mainfont).strip()

    # 4. Margin
    raw_margin = data.get("margin")
    margin_dict = {}
    if isinstance(raw_margin, dict):
        mx = raw_margin.get("x") or raw_margin.get("horizontal") or raw_margin.get("left") or raw_margin.get("right")
        my = raw_margin.get("y") or raw_margin.get("vertical") or raw_margin.get("top") or raw_margin.get("bottom")
        if mx is not None:
            margin_dict["x"] = str(mx)
        if my is not None:
            margin_dict["y"] = str(my)
    elif raw_margin:
        margin_dict["x"] = str(raw_margin)
        margin_dict["y"] = str(raw_margin)
    config["margin"] = margin_dict

    # 5. Columns
    columns = data.get("columns") or data.get("page_columns") or data.get("page-columns")
    if columns is not None:
        try:
            config["columns"] = int(columns)
        except ValueError:
            pass

    return config


class ReflowableConverter:
    """Converter for standard reflowable EPUBs using Pandoc and Typst."""

    def __init__(self, args: argparse.Namespace, config: Dict[str, Any]):
        self.args = args
        self.config = config

    def convert(self, epub_file: Path, output_pdf: Path, workspace_dir: Path):
        base_name = epub_file.stem
        typ_path = workspace_dir / f"{base_name}.typ"
        
        # 1. Resolve margin settings
        if self.args.margin:
            margin_x, margin_y = parse_cli_margin(self.args.margin)
        else:
            margin_cfg = self.config.get("margin", {})
            margin_x = margin_cfg.get("x")
            margin_y = margin_cfg.get("y")

        # Fallback margins if none specified
        if not margin_x and not margin_y:
            margin_x, margin_y = "1.0cm", "1.0cm"

        # 2. Merge metadata configuration for Pandoc template
        merged_meta = {
            "mainfont": self.args.font or self.config.get("mainfont"),
            "pagesize": self.args.page_size or self.config.get("pagesize") or "a5",
            "fontsize": self.args.font_size or self.config.get("fontsize"),
            "margin": {
                "x": margin_x,
                "y": margin_y
            } if (margin_x and margin_y) else (margin_x or margin_y),
            "columns": self.args.columns if self.args.columns is not None else (self.config.get("columns") or 1),
        }
        # Remove empty metadata
        merged_meta = {k: v for k, v in merged_meta.items() if v is not None}

        # Write merged metadata to a temporary file in the workspace
        meta_yaml_path = workspace_dir / "temp_metadata.yaml"
        meta_yaml_path.write_text(yaml.safe_dump(merged_meta), encoding="utf-8")

        # 3. Run Pandoc to generate intermediate Typst file
        print(f"Generating {typ_path.name} from {epub_file.name} using Pandoc...")
        try:
            cmd = [
                "pandoc", str(epub_file),
                "--metadata-file", str(meta_yaml_path),
                "-o", str(typ_path),
                "--standalone"
            ]
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error during Pandoc conversion: {e}", file=sys.stderr)
            sys.exit(1)

        # 4. Post-processing (Cleanups)
        print(f"Post-processing Typst markup...")
        content = typ_path.read_text(encoding="utf-8")

        # 4.1 Remove lines that only contain <*.xhtml>
        content = re.sub(r"^<.*\.xhtml>\s*$", "", content, flags=re.MULTILINE)

        # 4.2 Remove references to missing images to prevent Typst compilation failure
        def remove_missing_image(match):
            img_path_str = match.group("path")
            if not (typ_path.parent / img_path_str).exists():
                print(f"  Note: Missing image '{img_path_str}' reference removed.")
                return ""
            return match.group(0)

        content = re.sub(r'#box\(image\("(?P<path>[^"]+)"\)\)\s*', remove_missing_image, content)
        content = re.sub(r'image\("(?P<path>[^"]+)"\)', remove_missing_image, content)

        # 4.3 Remove links to missing labels
        all_label_instances = re.findall(r"<([a-zA-Z0-9_:.#-]+)>", content)
        link_instances = re.findall(r"#link\(<([a-zA-Z0-9_:.#-]+)>\)", content)

        instance_counts = {}
        for l in all_label_instances:
            instance_counts[l] = instance_counts.get(l, 0) + 1

        link_counts = {}
        for l in link_instances:
            link_counts[l] = link_counts.get(l, 0) + 1

        defined_labels = {l for l, count in instance_counts.items() if count > link_counts.get(l, 0)}

        def remove_missing_link(match):
            label = match.group(1)
            text = match.group(2)
            if label not in defined_labels:
                print(f"  Note: Missing label '<{label}>' link for '{text}' removed.")
                return text
            return match.group(0)

        content = re.sub(r"#link\(<([a-zA-Z0-9_:.#-]+)>\)\[([^\]]+)\]", remove_missing_link, content)
        typ_path.write_text(content, encoding="utf-8")

        # 5. Typst Compilation
        print(f"Compiling PDF via Typst...")
        typst_cmd = ["typst", "compile", str(typ_path), str(output_pdf)]
        if self.args.font_path:
            typst_cmd += ["--font-path", str(self.args.font_path)]
            
        try:
            subprocess.run(typst_cmd, check=True)
            print(f"Success! PDF compiled to: {output_pdf}")
        except subprocess.CalledProcessError as e:
            print(f"Error during Typst compilation: {e}", file=sys.stderr)
            sys.exit(1)


class FixedLayoutConverter:
    """Converter for fixed-layout (SVG/Image-only, Manga, Comic) EPUBs."""

    def __init__(self, args: argparse.Namespace, config: Dict[str, Any]):
        self.args = args
        self.config = config

    def convert(self, epub_file: Path, output_pdf: Path, workspace_dir: Path):
        print(f"Opening Fixed-Layout EPUB: {epub_file.name}")
        try:
            with zipfile.ZipFile(epub_file, "r") as z:
                # 1. Locate and parse OPF file
                opf_path = "item/standard.opf"
                if opf_path not in z.namelist():
                    opf_candidates = [n for n in z.namelist() if n.endswith(".opf")]
                    if not opf_candidates:
                        raise FileNotFoundError("Could not find OPF file inside EPUB.")
                    opf_path = opf_candidates[0]
                    
                opf_data = z.read(opf_path)
                root = ET.fromstring(opf_data)
                ns = {"opf": "http://www.idpf.org/2007/opf"}
                
                # 2. Parse Spine
                spine = find_tag(root, "spine", ns)
                if spine is None:
                    raise ValueError("Could not find spine in OPF.")
                itemrefs = [itemref.attrib.get("idref") for itemref in find_all_tags(spine, "itemref", ns)]
                
                # 3. Parse Manifest
                manifest = find_tag(root, "manifest", ns)
                if manifest is None:
                    raise ValueError("Could not find manifest in OPF.")
                manifest_map = {item.attrib.get("id"): item.attrib.get("href") for item in find_all_tags(manifest, "item", ns)}
                
                opf_parent = PurePosixPath(opf_path).parent
                
                # 4. Determine viewport dimensions (aspect ratio) from first few pages
                width, height = 1444, 2048  # defaults
                found_dimensions = False
                
                for idref in itemrefs[:10]:
                    href = manifest_map.get(idref)
                    if not href:
                        continue
                    xhtml_path = normalize_zip_path(str(opf_parent), href)
                    if xhtml_path in z.namelist():
                        content = z.read(xhtml_path).decode("utf-8", errors="ignore")
                        # Look for meta viewport
                        viewport_match = re.search(
                            r'<meta\s+name=["\']viewport["\']\s+content=["\']([^"\']+)["\']', content, re.IGNORECASE
                        )
                        if viewport_match:
                            vp_content = viewport_match.group(1)
                            w_match = re.search(r"width\s*=\s*(\d+)", vp_content)
                            h_match = re.search(r"height\s*=\s*(\d+)", vp_content)
                            if w_match and h_match:
                                width, height = int(w_match.group(1)), int(h_match.group(1))
                                found_dimensions = True
                                break
                        
                        # Look for SVG viewBox
                        viewbox_match = re.search(
                            r'viewBox\s*=\s*["\']\s*0\s+0\s+(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*["\']', content, re.IGNORECASE
                        )
                        if viewbox_match:
                            width, height = int(float(viewbox_match.group(1))), int(float(viewbox_match.group(2)))
                            found_dimensions = True
                            break
                
                if found_dimensions:
                    print(f"Detected native page size aspect ratio: {width}x{height} (Ratio: {width/height:.4f})")
                else:
                    print(f"Could not automatically detect aspect ratio; using default: {width}x{height}")
                    
                # 5. Extract images in spine order
                images_to_embed = []
                for i, idref in enumerate(itemrefs):
                    href = manifest_map.get(idref)
                    if not href:
                        print(f"Warning: No manifest entry found for spine item {idref}")
                        continue
                        
                    xhtml_path = normalize_zip_path(str(opf_parent), href)
                    if xhtml_path not in z.namelist():
                        print(f"Warning: XHTML file {xhtml_path} not found in ZIP")
                        continue
                        
                    xhtml_content = z.read(xhtml_path).decode("utf-8", errors="ignore")
                    
                    # Extract image reference path (supports standard svg:image or html:img)
                    img_href = None
                    img_match = re.search(r'<image\s+[^>]*(?:href|xlink:href)\s*=\s*["\']([^"\']+)["\']', xhtml_content, re.IGNORECASE)
                    if img_match:
                        img_href = img_match.group(1)
                    else:
                        img_match = re.search(r'<img\s+[^>]*src\s*=\s*["\']([^"\']+)["\']', xhtml_content, re.IGNORECASE)
                        if img_match:
                            img_href = img_match.group(1)
                        
                    if not img_href:
                        print(f"Warning: No image reference found in {xhtml_path}")
                        continue
                        
                    xhtml_parent = PurePosixPath(xhtml_path).parent
                    full_img_path = normalize_zip_path(str(xhtml_parent), img_href)
                    
                    if full_img_path not in z.namelist():
                        print(f"Warning: Image file {full_img_path} not found in ZIP")
                        continue
                        
                    # Extract image into our workspace directory
                    ext = Path(full_img_path).suffix
                    extracted_filename = f"page_{i:04d}{ext}"
                    extracted_path = workspace_dir / extracted_filename
                    
                    extracted_path.write_bytes(z.read(full_img_path))
                    images_to_embed.append(extracted_filename)
                    
                print(f"Extracted {len(images_to_embed)} images successfully.")
                
                # 6. Format Typst Page Configuration
                page_size = self.args.page_size or self.config.get("pagesize") or "original"
                if page_size.lower() == "original":
                    # Scale viewport to realistic physical dimensions (max height 25.0cm)
                    scale = 25.0 / height
                    w_cm = width * scale
                    h_cm = height * scale
                    typst_page_config = f"width: {w_cm:.2f}cm, height: {h_cm:.2f}cm"
                    print(f"Output PDF page size: Custom ({w_cm:.2f}cm x {h_cm:.2f}cm) to match original aspect ratio.")
                else:
                    typst_page_config = f'paper: "{page_size}"'
                    print(f"Output PDF page size: {page_size.upper()} (Fit: {self.args.fit})")
                    
                # 7. Generate Typst Document
                typst_file = workspace_dir / "document.typ"
                typst_content = f"""#set page(
  {typst_page_config},
  margin: (top: 0pt, bottom: 0pt, left: 0pt, right: 0pt),
)
"""
                for img in images_to_embed:
                    typst_content += f'#image("{img}", width: 100%, height: 100%, fit: "{self.args.fit}")\n'
                    
                typst_file.write_text(typst_content, encoding="utf-8")
                
                # 8. Compile using Typst
                print("Compiling PDF via Typst...")
                typst_cmd = ["typst", "compile", str(typst_file), str(output_pdf)]
                if self.args.font_path:
                    typst_cmd += ["--font-path", str(self.args.font_path)]
                    
                result = subprocess.run(typst_cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    print(f"Success! PDF compiled to: {output_pdf}")
                else:
                    print("Error during Typst compilation:", file=sys.stderr)
                    print(result.stderr, file=sys.stderr)
                    sys.exit(1)
                    
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Convert EPUB files to PDF using Typst, automatically detecting layout style."
    )
    parser.add_argument("epub", help="Path to the input .epub file")
    parser.add_argument("-o", "--output", help="Path to the output .pdf file")
    parser.add_argument(
        "-l", "--layout",
        default="auto",
        choices=["auto", "fixed", "reflow"],
        help="Layout mode: 'auto' (detect layout), 'fixed' (manga/comic style), 'reflow' (textbook style)"
    )
    parser.add_argument("-c", "--config", help="Path to configuration file (e.g. metadata.yaml)")
    parser.add_argument("--page-size", help="Page size override (e.g., 'a5', 'a4', 'original')")
    parser.add_argument("--font-size", help="Font size override (e.g. '12pt', reflow mode only)")
    parser.add_argument("--font", help="Main font name (reflow mode only)")
    parser.add_argument(
        "--font-path",
        default=get_default_font_path(),
        help="Directory to search for fonts in Typst"
    )
    parser.add_argument("--margin", help="Margin override (e.g. '1cm' or 'x:1.0cm,y:1.5cm')")
    parser.add_argument("--columns", type=int, help="Number of columns (reflow mode only)")
    parser.add_argument(
        "--fit",
        default="contain",
        choices=["contain", "cover", "stretch"],
        help="Image fit mode (fixed layout mode only): 'contain', 'cover', or 'stretch'"
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep intermediate Typst source markup and images inside a <book_name>_typst directory"
    )

    args = parser.parse_args()

    epub_file = Path(args.epub)
    if not epub_file.exists():
        print(f"Error: Input file '{epub_file}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # 1. Determine output PDF path
    if args.output:
        output_pdf = Path(args.output)
    else:
        output_pdf = Path("output") / f"{epub_file.stem}.pdf"

    # 2. Detect Layout Mode
    layout = args.layout
    if layout == "auto":
        print("Detecting EPUB layout type...")
        layout = detect_layout(epub_file)
        print(f"Detected layout: {layout.upper()}")

    # 3. Load Configuration File
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path, layout=layout)

    # 4. Check dependencies based on layout mode
    needs_pandoc = (layout == "reflow")
    if not check_dependencies(needs_pandoc):
        sys.exit(1)

    # 5. Ensure output parent directory exists
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    # 6. Execute conversion inside either temporary or kept workspace directory
    if args.keep_temp:
        workspace_dir = output_pdf.parent / f"{output_pdf.stem}_typst"
        # Cleanup prior permanent workspace if it exists
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        if layout == "reflow":
            converter = ReflowableConverter(args, config)
            converter.convert(epub_file, output_pdf, workspace_dir)
        else:
            converter = FixedLayoutConverter(args, config)
            converter.convert(epub_file, output_pdf, workspace_dir)
        print(f"Temporary source files kept in: {workspace_dir}")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace_dir = Path(temp_dir)
            if layout == "reflow":
                converter = ReflowableConverter(args, config)
                converter.convert(epub_file, output_pdf, workspace_dir)
            else:
                converter = FixedLayoutConverter(args, config)
                converter.convert(epub_file, output_pdf, workspace_dir)


if __name__ == "__main__":
    main()
