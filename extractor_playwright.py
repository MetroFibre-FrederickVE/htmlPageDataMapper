# extractor_playwright.py
import argparse
import json
from pathlib import Path
from urllib.parse import urlparse
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from rich.console import Console
from rich.panel import Panel

console = Console()

async def capture_json_responses(page, url: str, timeout_sec: int = 25):
    """Capture network responses that look like JSON APIs"""
    json_responses = []

    def is_likely_json_api(response):
        content_type = response.headers.get("content-type", "").lower()
        url_path = urlparse(response.url).path.lower()
        return (
            "json" in content_type or
            response.url.endswith((".json", ".jsonp")) or
            any(kw in url_path for kw in ["/api/", "/data/", "/status", "/outages", "/faults", "/regions"])
        ) and response.status == 200

    async def handle_response(response):
        if not is_likely_json_api(response):
            return

        try:
            text = await response.text()
            data = json.loads(text)
            json_responses.append({
                "url": response.url,
                "status": response.status,
                "size_bytes": len(text),
                "data": data,
                "content_type": response.headers.get("content-type", "unknown")
            })
            console.print(f"[green]Captured JSON API:[/green] {response.url}")
        except json.JSONDecodeError:
            console.print(f"[yellow]Non-JSON response (but matched filter):[/yellow] {response.url}")
        except Exception as e:
            console.print(f"[red]Error parsing response:[/red] {e}")

    page.on("response", handle_response)

    console.print(f"[bold blue]Loading page...[/bold blue] {url}")
    try:
        await page.goto(url, wait_until="networkidle", timeout=timeout_sec * 1000)
        # Give extra time for late API calls (common on status pages)
        await asyncio.sleep(6)
    except PlaywrightTimeout:
        console.print("[yellow]Timeout reached — partial load, checking captured data...[/yellow]")
    except Exception as e:
        console.print(f"[red]Page load failed:[/red] {e}")
        return []

    return json_responses

def suggest_filename(data, index: int, source_url: str = "") -> str:
    """Smart filename guessing from JSON content"""
    if not isinstance(data, (dict, list)):
        return f"response_{index:03d}"

    keys_lower = {k.lower(): k for k in data} if isinstance(data, dict) else {}

    priorities = [
        "title", "name", "type", "status", "category", "outages", "faults",
        "regions", "incidents", "network", "config", "data"
    ]

    for prio in priorities:
        if prio in keys_lower:
            value = data[keys_lower[prio]]
            if isinstance(value, str) and 3 <= len(value) <= 45:
                clean = "".join(c if c.isalnum() else "_" for c in value.lower().strip())
                return clean.strip("_")

    # Fallback to domain + index
    domain = urlparse(source_url).netloc.replace(".", "_")
    return f"{domain}_data_{index:03d}"

async def main():
    parser = argparse.ArgumentParser(description="HtmlPageJsonExtractor (Playwright) - Capture JSON from dynamic pages")
    parser.add_argument("url", help="Target URL")
    parser.add_argument("--output-dir", "-o", default="./extracted", help="Where to save JSON files")
    parser.add_argument("--timeout", type=int, default=30, help="Page load timeout (seconds)")
    parser.add_argument("--interactive", "-i", action="store_true", help="Ask for custom filenames")
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 HtmlPageJsonExtractor/1.0 (Personal Project)",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        captured = await capture_json_responses(page, args.url, args.timeout)

        await browser.close()

    if not captured:
        console.print(Panel(
            "[yellow]No JSON API responses captured.[/yellow]\n\n"
            "Possible reasons:\n"
            "• Data is rendered purely client-side without separate API calls\n"
            "• Anti-bot protection\n"
            "• Very late loading (>30s)\n\n"
            "Next steps:\n"
            "1. Increase --timeout\n"
            "2. Try DOM extraction instead\n"
            "3. Open devtools → Network tab and look for .json / api calls manually",
            title="No Data Found", border_style="yellow"
        ))
        return

    console.print(f"\n[bold green]Captured {len(captured)} JSON responses![/bold green]\n")

    for i, item in enumerate(captured, 1):
        data = item["data"]
        suggested = suggest_filename(data, i, item["url"])

        console.print(f"[bold]{i}.[/bold] {item['url']}")
        console.print(f"   Suggested name: [cyan]{suggested}.json[/cyan]")
        console.print(f"   Size: {item['size_bytes']/1024:.1f} KB | Status: {item['status']}")

        if args.interactive:
            custom = console.input("   Custom name (Enter to accept suggested): ").strip()
            if custom:
                suggested = "".join(c if c.isalnum() or c in "-_" else "_" for c in custom)

        filename = f"{suggested}.json"
        path = out_dir / filename

        # Avoid overwrite
        counter = 1
        while path.exists():
            path = out_dir / f"{suggested}_{counter}.json"
            counter += 1

        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            console.print(f"   → Saved: [green]{path.name}[/green]\n")
        except Exception as e:
            console.print(f"   → Save failed: [red]{e}[/red]")

if __name__ == "__main__":
    asyncio.run(main())