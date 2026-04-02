# EPUB to Typst Converter

This project allows you to convert EPUB books to professional PDF documents using **Pandoc** and **Typst**.

## Setup

1. Ensure **Pandoc** and **Typst** are installed on the system.
2. Edit **metadata.yaml** to customize the font, margin, and other settings.
3. Ensure you have the **芫荽 (Iansui)** font installed on your system.

## How to Rebuild a Book

Run the **rebuild.py** Python script with the path to the EPUB file.

### Basic Usage

The script will generate a `.typ` and `.pdf` file in the default **books/** directory:

```bash
python3 rebuild.py books/笑傲江湖.epub
```

### Custom Output Directory

You can specify a different output directory using the **--out** flag:

```bash
python3 rebuild.py books/笑傲江湖.epub --out my_pdfs/
```

### Script Features

The script automatically:

1. Regenerates the Typst file from your metadata settings.
2. Resolves any unattached label warnings (labels like `<*.xhtml>`).
3. Compiles the final PDF with support for local system fonts.

## File Structure

- **books/**: Recommended directory for EPUB sources and generated outputs.
- **metadata.yaml**: Central configuration for font and layout.
- **rebuild.py**: The Python-based automation script.
- **README.md**: Project documentation.
