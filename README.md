# HtmlPageJsonExtractor

Extract JSON from modern web pages using Playwright.

## Features
- Extracts `window.nsData` from SPAs
- Captures API responses
- Smart naming
- Interactive mode
- Handles invalid JSON

## Setup
```bash
python -m venv venv
source venv/bin/activate
pip install playwright rich
playwright install
```

## Run
```bash
python extractor_playwright.py https://example.com
```
## Output
JSON files will be output into `{current_dir}/extracted/`