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

### Initial Development Setup (IMPORTANT!)

**⚠️ Critical**: Gradio custom components require building before they can be used. The frontend assets must be compiled and the component installed in your Python environment.

#### Complete Setup Steps:

1. **Create and activate a virtual environment** (in the project root):
   ```bash
   # Create venv in project root
   python3 -m venv .venv

   # Activate it (macOS/Linux)
   source .venv/bin/activate

   # Or on Windows
   .venv\Scripts\activate
   ```

2. **Install frontend dependencies**:
   ```bash
   cd frontend
   npm install
   cd ..
   ```

3. **Install Python dependencies**:
   ```bash
   # Install core build dependencies
   .venv/bin/pip install gradio build ruff

   # Install demo dependencies (optional, only if running demos)
   .venv/bin/pip install torch transformers pdf2image pytesseract
   ```

   **Gotcha**: The `build` package is required for `python -m build` and `ruff` is required by the Gradio build process for code formatting.

4. **Install the component in development mode**:
   ```bash
   .venv/bin/pip install -e .
   ```

   **Important**: The component must be installed before building, otherwise `gradio cc build` will fail with "package is not installed" error.

5. **Build the custom component**:
   ```bash
   # From the project root directory
   PATH="$PWD/.venv/bin:$PATH" .venv/bin/python -m gradio cc build
   ```

   **Gotcha**: The `PATH` must include your venv's bin directory so that `ruff` can be found during the build process. Without this, you'll get `FileNotFoundError: [Errno 2] No such file or directory: 'ruff'`.

   This command will:
   - Build the frontend (compiles Svelte components to JavaScript)
   - Generate documentation files (`demo/space.py`, `README.md`)
   - Build the Python wheel package in `dist/`

   The `-e` flag from step 4 installs in "editable" mode, so Python code changes are immediately reflected without reinstalling. However, **frontend changes require rebuilding** (step 5).

6. **Run the demo**:
   ```bash
   cd demo
   ../.venv/bin/python app.py
   # Or use _app.py for the custom demo with document QA
   ../.venv/bin/python _app.py
   ```

#### Common Issues and Solutions:

- **404 errors in browser** (`style.css`, `index.js`, `manifest.json` not found):
  - **Cause**: Frontend hasn't been built yet
  - **Solution**: Run `gradio cc build` (step 3 above)

- **FileNotFoundError: 'ruff'** during build:
  - **Cause**: `ruff` not in PATH when subprocess is spawned
  - **Solution**: Either install `ruff` globally or use `PATH="$PWD/demo/.venv/bin:$PATH"` prefix

- **No module named 'build'**:
  - **Cause**: Missing build dependency
  - **Solution**: `pip install build`

- **Frontend changes not appearing**:
  - **Cause**: Frontend is compiled, not live-reloaded
  - **Solution**: Re-run `gradio cc build` after Svelte changes

### Building and Publishing

This package uses Python's `hatchling` build system:

```bash
# Build the package (after running gradio cc build)
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
```

**Note**: Use `gradio cc build` (not npm) to build the frontend, as it integrates with Gradio's custom component system.

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

- Python package version is in `pyproject.toml` (`version = "0.0.23"`)
- Frontend package version is in `frontend/package.json` (`version = "0.2.1"`)
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
