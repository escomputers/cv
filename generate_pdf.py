#!/usr/bin/env python3
"""
Generate the canonical PDF version of the resume from cv-printable.html.

The PDF settings are intentionally encoded here so nobody has to remember
Chrome print-dialog options:
- A4
- zero browser-added margins
- backgrounds/colors enabled
- no browser header/footer
- CSS @page honored
- light color scheme
"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
from threading import Thread

try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
except ImportError:
    raise SystemExit(
        "Playwright is not installed.\n"
        "Run once:\n"
        "  python3 -m pip install -r requirements-pdf.txt\n"
        "Then, if needed:\n"
        "  python3 -m playwright install chromium"
    )


ROOT = Path(__file__).resolve().parent
DEFAULT_INPUT = ROOT / "cv-printable.html"
DEFAULT_OUTPUT = ROOT / "static" / "pdf" / "Emiliano-Spada-Resume.pdf"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        pass


def start_local_server() -> tuple[ThreadingHTTPServer, str]:
    handler = partial(QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Printable HTML source (default: cv-printable.html)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="PDF output path",
    )
    args = parser.parse_args()

    input_html = args.input.resolve()
    output_pdf = args.output.resolve()

    if not input_html.exists():
        raise SystemExit(f"Input file not found: {input_html}")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        # Prefer Playwright's bundled Chromium. If it has not been installed,
        # fall back to a locally installed Chrome/Chromium.
        try:
            browser = pw.chromium.launch(headless=True)
        except PlaywrightError:
            browser = None

            # Google Chrome installed in the normal way (works on macOS too).
            try:
                browser = pw.chromium.launch(channel="chrome", headless=True)
            except PlaywrightError:
                pass

            # Common Chromium executable names/locations.
            if browser is None:
                candidates = [
                    shutil.which("chromium"),
                    shutil.which("chromium-browser"),
                    shutil.which("google-chrome"),
                    shutil.which("google-chrome-stable"),
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                ]
                for executable in candidates:
                    if executable and Path(executable).exists():
                        try:
                            browser = pw.chromium.launch(
                                executable_path=executable,
                                headless=True,
                            )
                            break
                        except PlaywrightError:
                            continue

            if browser is None:
                raise SystemExit(
                    "No usable Chromium/Chrome installation found.\n"
                    "Run:\n"
                    "  python3 -m playwright install chromium"
                )

        page = browser.new_page(
            viewport={"width": 1440, "height": 2000},
            device_scale_factor=1,
        )
        page.set_default_timeout(60_000)

        failed_requests: list[str] = []

        def record_failed_request(request) -> None:
            failed_requests.append(request.url)

        page.on("requestfailed", record_failed_request)

        page.emulate_media(media="print", color_scheme="light")

        server, base_url = start_local_server()
        try:
            relative_input = input_html.relative_to(ROOT).as_posix()
        except ValueError:
            browser.close()
            server.shutdown()
            raise SystemExit(f"Input HTML must be inside the repository root: {ROOT}")

        page.goto(f"{base_url}/{relative_input}", wait_until="networkidle")

        # Wait until web fonts and images have finished resolving.
        page.evaluate("() => document.fonts ? document.fonts.ready : Promise.resolve()")
        page.wait_for_function(
            "() => Array.from(document.images).every(img => img.complete)"
        )

        broken_images = page.evaluate(
            """() => Array.from(document.images)
                .filter(img => img.naturalWidth === 0)
                .map(img => img.src)"""
        )
        broken_stylesheets = page.evaluate(
            """() => Array.from(document.querySelectorAll('link[rel="stylesheet"]'))
                .filter(link => !link.sheet)
                .map(link => link.href)"""
        )

        # Missing local assets must never produce a silently broken PDF.
        local_failures = [
            url
            for url in (failed_requests + broken_images + broken_stylesheets)
            if url.startswith(base_url)
        ]
        if local_failures:
            browser.close()
            server.shutdown()
            details = "\n".join(f"  - {url}" for url in sorted(set(local_failures)))
            raise SystemExit(f"Missing local assets; PDF was not generated:\n{details}")

        page.pdf(
            path=str(output_pdf),
            format="A4",
            scale=1.0,
            print_background=True,
            display_header_footer=False,
            prefer_css_page_size=True,
            margin={
                "top": "0",
                "right": "0",
                "bottom": "0",
                "left": "0",
            },
        )

        browser.close()
        server.shutdown()

    if not output_pdf.exists() or output_pdf.stat().st_size == 0:
        raise SystemExit("PDF generation failed: output file is missing or empty.")

    print(f"PDF generated: {output_pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
