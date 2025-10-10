# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Gradio custom component (`gradio_pdf`) that provides a PDF viewer component for Gradio applications. It allows users to easily display and navigate PDFs in Gradio interfaces, with support for file uploads, page navigation, and integration with Gradio's event system.

## Architecture

### Component Structure

This is a **Gradio custom component** that follows Gradio's dual-architecture pattern:

1. **Backend (Python)**: `/backend/gradio_pdf/`
   - `pdf.py`: Defines the `PDF` component class that extends Gradio's `Component` base class
   - Handles data preprocessing (converting `FileData` to file paths) and postprocessing (converting paths back to `FileData`)
   - Exposes two events: `change` and `upload`

2. **Frontend (Svelte)**: `/frontend/`
   - `Index.svelte`: Main component implementation
   - `Example.svelte`: Example display component
   - `PdfUploadText.svelte`: Upload UI text component
   - Uses `pdfjs-dist` library to render PDFs on a canvas element
   - Handles PDF rendering, page navigation, and user interactions

3. **Demo**: `/demo/`
   - `_app.py`: Example application showing document question-answering
   - `app.py`: Auto-generated demo wrapper for documentation

### Key Technical Details

- **PDF Rendering**: Uses Mozilla's PDF.js library (`pdfjs-dist`) loaded via CDN worker
- **Character Maps**: Chinese/Japanese/Korean character support via HuggingFace-hosted cmaps
- **Data Flow**: File paths are passed between backend and frontend via Gradio's `FileData` model
- **Starting Page**: Component supports `starting_page` parameter to control initial page display (defaults to 1)

## Development Commands

### Building and Publishing

This package uses Python's `hatchling` build system:

```bash
# Build the package
python -m build

# Publish to PyPI
twine upload dist/*
```

### Running the Demo

```bash
# Run the example application
python demo/_app.py
```

The demo requires additional dependencies:
- `pdf2image`: For converting PDFs to images
- `transformers`: For the document QA model
- `torch`: Required by transformers

### Frontend Development

The frontend uses Node.js and Gradio's build tooling:

```bash
cd frontend
npm install
# Build commands would be handled by Gradio's tooling
```

## Important Implementation Notes

### Backend Component (`backend/gradio_pdf/pdf.py`)

- The component extends `gradio.components.base.Component`
- `preprocess()`: Extracts the file path from `FileData` payload, returns `None` if no file
- `postprocess()`: Wraps file path string into `FileData` object
- The `height` parameter controls PDF scaling in the frontend
- `starting_page` must be validated to be within `[1, numPages]` range

### Frontend Component (`frontend/Index.svelte`)

- PDF.js worker is loaded from CDN: `https://cdn.jsdelivr.net/gh/freddyaboulton/gradio-pdf@main/pdf.worker.min.mjs`
- Character maps loaded from: `https://huggingface.co/datasets/freddyaboulton/bucket/resolve/main/cmaps/`
- Page rendering uses canvas with viewport scaling based on `height` prop
- Current page is reactive and constrained: `Math.min(Math.max(starting_page, 1), numPages)`
- The component dispatches `change` event when value changes and `upload` event on file upload

### Version Management

- Python package version is in `pyproject.toml` (`version = "0.0.22"`)
- Frontend package version is in `frontend/package.json` (`version = "0.2.0"`)
- These versions should be kept in sync when publishing

## Dependencies

### Python (Backend)
- `gradio>=4.0,<6.0`: Core framework

### JavaScript (Frontend)
- `pdfjs-dist@4.2.67`: PDF rendering engine
- `@gradio/*`: Various Gradio UI packages (atoms, button, upload, etc.)

## File Locations

- Main component implementation: `backend/gradio_pdf/pdf.py`
- Frontend UI: `frontend/Index.svelte`
- Example usage: `demo/_app.py`
- Package configuration: `pyproject.toml`
- Frontend config: `frontend/package.json`
