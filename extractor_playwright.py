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
        # Wait until network is idle and DOM is fully loaded
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
        await page.wait_for_load_state("networkidle", timeout=timeout_sec * 1000)
        await asyncio.sleep(3)  # Extra wait for React hydration
    except PlaywrightTimeout:
        console.print("[yellow]Timeout reached — partial load, checking captured data...[/yellow]")
    except Exception as e:
        console.print(f"[red]Page load failed:[/red] {e}")
        return []

    return json_responses

# NEW: Extract window.nsData directly via JavaScript in browser
async def extract_nsdata_from_window(page):
    try:
        # Try to get window.nsData
        result = await page.evaluate("() => window.nsData")
        if result:
            console.print("[bold green]✅ Successfully extracted nsData from window![/bold green]")
            return result
        else:
            console.print("[yellow]window.nsData is undefined[/yellow]")
            return None
    except Exception as e:
        console.print(f"[red]Failed to evaluate window.nsData: {e}[/red]")
        return None

def suggest_filename(data, index: int, source_url: str = "") -> str:
    """Smart filename guessing"""
    if not isinstance(data, (dict, list)):
        return f"response_{index:03d}"

    if isinstance(data, dict):
        if "ftth" in data or "outages" in data or "maintenance" in data:
            return "network_status"
        if "statusTypes" in data or "areas" in data:
            return "network_config"

        keys_lower = {k.lower(): k for k in data}
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

        if "data" in data and isinstance(data["data"], dict):
            return suggest_filename(data["data"], index)

    domain = urlparse(source_url).netloc.replace(".", "_")
    return f"{domain}_data_{index:03d}"

def save_json_with_fallback(obj, path: Path, indent: int = 2):
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False)
        console.print(f"✓ Saved valid JSON: {path}")
    except Exception as e:
        partial_path = path.with_suffix(".partial.json")
        with partial_path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, indent=indent, ensure_ascii=False, default=str)
        console.print(f"✗ Invalid JSON → saved as partial: {partial_path} ({e})")

async def main():
    parser = argparse.ArgumentParser(description="HtmlPageJsonExtractor (Playwright) - Extract nsData & network JSON")
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

        # Extract nsData from window
        nsdata = await extract_nsdata_from_window(page)

        await browser.close()

    # Combine results
    all_json = captured
    if nsdata:
        all_json.append({
            "url": args.url + " (window.nsData)",
            "status": 200,
            "size_bytes": len(json.dumps(nsdata)),
            "data": nsdata,
            "content_type": "application/json (window)"
        })

    if not all_json:
        console.print(Panel(
            "[red]No JSON data found.[/red]\n\n"
            "Check if the page uses anti-bot protection or if nsData is loaded differently.",
            title="No Data Found", border_style="red"
        ))
        return

    console.print(f"\n[bold green]Extracted {len(all_json)} JSON object(s)![/bold green]\n")

    for i, item in enumerate(all_json, 1):
        data = item["data"]
        suggested = suggest_filename(data, i, item["url"])

        console.print(f"[bold]{i}.[/bold] {item['url']}")
        console.print(f"   Suggested name: [cyan]{suggested}.json[/cyan]")
        console.print(f"   Size: {item['size_bytes']/1024:.1f} KB")

        if args.interactive:
            custom = console.input("   Custom name (Enter to accept): ").strip()
            if custom:
                suggested = "".join(c if c.isalnum() or c in "-_" else "_" for c in custom)

        filename = f"{suggested}.json"
        path = out_dir / filename

        counter = 1
        while path.exists():
            path = out_dir / f"{suggested}_{counter}.json"
            counter += 1

        save_json_with_fallback(data, path)

if __name__ == "__main__":
    asyncio.run(main())