# EPUB & PDF Tools

A simple toolkit to package images into EPUB files, and convert EPUB files to high-quality PDF documents using **Typst** and **Pandoc**:

```
[Folder of Images] ──(img2epub.py)──> [EPUB Ebook] ──(epub2pdf.py)──> [High-Quality PDF]
```

---

## Requirements

1. **Python 3.11+** and **[uv](https://github.com/astral-sh/uv)** (recommended for zero-setup execution).
2. **[Typst](https://typst.app/)** installed and available in your system `PATH`.
3. **[Pandoc](https://pandoc.org/)** installed and available in your system `PATH` (only required for reflowable text EPUBs).

---

## 1. EPUB-to-PDF Converter (`epub2pdf.py`)

Converts EPUB files to high-quality PDF documents. It automatically detects whether the input EPUB is a **fixed-layout** book (e.g., Manga, Comic, or image-heavy eBook) or a **reflowable** text book and applies the appropriate layout engine.

### Quick Start

```bash
uv run epub2pdf.py path/to/book.epub
```

By default, the compiled PDF will be saved in `output/<book_name>.pdf`.

### Command-Line Options

```bash
uv run epub2pdf.py <epub_path> [options]
```

| Option | Description |
|---|---|
| `-o`, `--output` | Specify a custom path for the output `.pdf` file. |
| `-l`, `--layout` | Force conversion layout: `auto` (default), `reflow` (textbooks), or `fixed` (comics/manga). |
| `-c`, `--config` | Path to a custom configuration YAML file. |
| `--page-size` | Page size override (e.g., `a4`, `a5`, `original`, or custom dimension like `10cmx15cm`). |
| `--font-size` | Font size (e.g., `12pt`, only applies to `reflow` layout). |
| `--font` | Font name (only applies to `reflow` layout). |
| `--font-path` | Additional directory path for Typst to search for fonts (defaults to `~/Library/Fonts` on macOS). |
| `--margin` | Margin override (e.g. `1cm` or `x:1cm,y:1.5cm`). |
| `--columns` | Number of text columns (only applies to `reflow` layout). |
| `--fit` | Image fit style: `contain` (default), `cover`, or `stretch` (only applies to `fixed` layout). |
| `--keep-temp` | Keep intermediate Typst files and extracted images inside a `<book_name>_typst/` directory for debugging. |

### Configuration Files

The tool automatically searches for default layout-specific configuration files in the directory it is executed from:

* **Reflowable Books (`reflow`):** Searches for `reflow-config.yaml` $\rightarrow$ `metadata.yaml` $\rightarrow$ `epub2pdf.yaml`.
* **Fixed-Layout Books (`fixed`):** Searches for `fixed-config.yaml` $\rightarrow$ `metadata.yaml` $\rightarrow$ `epub2pdf.yaml`.

#### Example Configuration (`reflow-config.yaml`)

```yaml
---
mainfont: "芫荽"
pagesize: a5
fontsize: 14pt
margin:
    x: 0.5cm
    y: 0.5cm
columns: 1
---
```

---

## 2. Image-to-EPUB Compiler (`img2epub.py`)

Packages a directory of images (e.g., scanned Manga or Comic pages) into a valid fixed-layout EPUB 3 ebook. 

The compiler naturally sorts the image filenames, automatically reads the dimensions of each image using `Pillow` to establish correct page viewports, and designates the first page as the book cover.

### Quick Start

```bash
uv run img2epub.py path/to/images [options]
```

By default, the EPUB will be saved in `output/<directory_name>.epub`.

### Command-Line Options

```bash
uv run img2epub.py <image_dir> [options]
```

| Option | Description |
|---|---|
| `-o`, `--output` | Custom path for the output `.epub` file (defaults to `output/<image_dir_name>.epub`). |
| `-t`, `--title` | Title of the book (defaults to the directory name). |
| `-a`, `--author` | Author of the book (defaults to `Unknown`). |
| `-l`, `--language` | Language code (defaults to `ja`). |
| `-d`, `--direction` | Page progression direction: `ltr` or `rtl` (defaults to `rtl` for manga). |
