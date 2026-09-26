# Resume PDF pipeline

Run from the repository root:

```bash
python3 -m venv .env/ && source .env/bin/activate
python -m pip install -r requirements-pdf.txt
python generate_pdf.py
```

If Playwright cannot find a browser, run once:

```bash
python3 -m playwright install chromium
```

The generated file is:

```text
static/pdf/Emiliano-Spada-Resume.pdf
```

The generator fixes the print settings in code: A4, zero browser-added margins,
background graphics enabled, no browser headers/footers, light theme.
