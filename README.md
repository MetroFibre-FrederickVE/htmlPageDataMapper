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

## Example
<img width="1108" height="328" alt="image" src="https://github.com/user-attachments/assets/03c4e667-f616-4ef9-b3c6-5c235fe9f23e" />

#### Output
<img width="1565" height="833" alt="image" src="https://github.com/user-attachments/assets/f0cf4a54-c849-4b5b-9ff9-5369d17ba290" />

