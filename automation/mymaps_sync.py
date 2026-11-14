"""Send a TripPilot CSV to Google My Maps by driving YOUR Chrome on THIS Mac.

Runs locally only. It never sees your Google password: you sign in yourself, once,
in the browser window `login` opens, and the session is kept in ~/.trippilot/chrome-profile.

    python automation/mymaps_sync.py login
    python automation/mymaps_sync.py check
    python automation/mymaps_sync.py import trippilot_mymaps.csv --title "Kyoto 2 days"

My Maps has no public API, so this clicks through the web UI. Google can change that UI;
every step saves a screenshot to ~/.trippilot/logs/<time>/ so a broken step is easy to see.
"""

import argparse
import contextlib
import csv
import json
import re
import sys
import time
from pathlib import Path

HOME = Path.home() / ".trippilot"
PROFILE = HOME / "chrome-profile"
import os

MYMAPS = os.getenv("TRIPPILOT_MYMAPS_URL", "https://www.google.com/maps/d/?hl=en")  # English UI keeps texts stable


class NotLoggedIn(RuntimeError):
    pass


class StepFailed(RuntimeError):
    pass


def _browser(p, headless: bool):
    PROFILE.mkdir(parents=True, exist_ok=True)
    opts = dict(
        user_data_dir=str(PROFILE), headless=headless, locale="en-US",
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    try:  # real Google Chrome: Google accepts sign-ins there more readily than in test Chromium
        return p.chromium.launch_persistent_context(channel="chrome", **opts)
    except Exception:
        return p.chromium.launch_persistent_context(**opts)


def _logged_in(page) -> bool:
    page.goto(MYMAPS, wait_until="domcontentloaded")
    page.wait_for_timeout(2500)
    if "accounts.google.com" in page.url:
        return False
    return page.get_by_text(re.compile("create a new map", re.I)).count() > 0


class Run:
    """Numbered steps with a screenshot after each one."""

    def __init__(self, page):
        self.page = page
        self.dir = HOME / "logs" / time.strftime("%Y%m%d-%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.n = 0
        self.warnings: list[str] = []

    @contextlib.contextmanager
    def step(self, name: str, required: bool = True):
        self.n += 1
        shot = self.dir / f"{self.n:02d}-{re.sub(r'[^a-z0-9]+', '-', name.lower())}.png"
        try:
            yield
            self.page.screenshot(path=str(shot))
        except Exception as e:
            with contextlib.suppress(Exception):
                self.page.screenshot(path=str(shot))
            if required:
                raise StepFailed(f"Step {self.n} '{name}' failed: {e}. Screenshot: {shot}") from e
            self.warnings.append(f"'{name}' was skipped ({type(e).__name__}); do it by hand. Screenshot: {shot}")


def _click_text(scope, pattern: str, timeout: int = 15000):
    scope.get_by_text(re.compile(pattern, re.I)).first.click(timeout=timeout)


def _read_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def login(timeout_s: int = 300) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _browser(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if _logged_in(page):
            ctx.close()
            return {"ok": True, "message": "Already signed in."}
        print("Sign in to Google in the window that opened. Waiting up to", timeout_s, "seconds…", file=sys.stderr)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            page.wait_for_timeout(3000)
            if "accounts.google.com" not in page.url and page.get_by_text(re.compile("create a new map", re.I)).count():
                ctx.close()
                return {"ok": True, "message": "Signed in. The session is saved for next time."}
            if "accounts.google.com" not in page.url and "google.com/maps/d" not in page.url:
                page.goto(MYMAPS)
        ctx.close()
        return {"ok": False, "message": "Timed out waiting for sign-in."}


def check(headless: bool = True) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _browser(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        ok = _logged_in(page)
        ctx.close()
    return {"ok": ok, "message": "Signed in." if ok else "Not signed in. Run: python automation/mymaps_sync.py login"}


def import_csv(csv_path: str, title: str, headless: bool = False, group_by: str = "Category") -> dict:
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright

    path = Path(csv_path).expanduser().resolve()
    rows = _read_csv(path)
    names = [r["Name"] for r in rows if r.get("Name")]
    if not names:
        raise ValueError(f"No rows with a Name in {path}")

    with sync_playwright() as p:
        ctx = _browser(p, headless=headless)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        if not _logged_in(page):
            ctx.close()
            raise NotLoggedIn("Not signed in to Google. Run: python automation/mymaps_sync.py login")
        run = Run(page)
        try:
            with run.step("create new map"):
                try:  # My Maps often opens the new map in a new tab
                    with ctx.expect_page(timeout=8000) as new_tab:
                        _click_text(page, r"create a new map")
                    page = run.page = new_tab.value
                except PWTimeout:
                    pass
                page.wait_for_load_state("domcontentloaded")
                page.get_by_text(re.compile("untitled map", re.I)).first.wait_for(timeout=30000)

            with run.step("set map title", required=False):
                _click_text(page, r"^untitled map$")
                dialog = page.get_by_role("dialog")
                dialog.locator("input").first.fill(title, timeout=8000)
                dialog.get_by_role("button", name=re.compile("save", re.I)).click(timeout=8000)

            with run.step("open import"):
                _click_text(page, r"^import$")

            with run.step("upload csv"):
                picker = page.frame_locator("iframe[src*='picker']").first
                file_input = picker.locator("input[type=file]").first
                try:
                    file_input.set_input_files(str(path), timeout=20000)
                except Exception:
                    with page.expect_file_chooser(timeout=15000) as fc:
                        picker.get_by_role("button", name=re.compile("browse|select a file", re.I)).first.click()
                    fc.value.set_files(str(path))

            with run.step("choose location column (Address)"):
                page.get_by_text(re.compile("choose columns to position", re.I)).first.wait_for(timeout=60000)
                page.get_by_role("checkbox", name=re.compile(r"^address$", re.I)).first.check(timeout=10000)
                page.get_by_role("button", name=re.compile(r"^continue$", re.I)).first.click(timeout=10000)

            with run.step("choose title column (Name)"):
                page.get_by_text(re.compile("choose a column to title", re.I)).first.wait_for(timeout=30000)
                page.get_by_role("radio", name=re.compile(r"^name$", re.I)).first.check(timeout=10000)
                page.get_by_role("button", name=re.compile(r"^finish$", re.I)).first.click(timeout=10000)

            with run.step("wait for import"):
                page.get_by_text(names[0], exact=True).first.wait_for(timeout=90000)
                page.wait_for_timeout(2000)

            not_shown = 0
            m = page.get_by_text(re.compile(r"\d+ rows? (couldn.t|could not) be shown", re.I))
            if m.count():
                not_shown = int(re.search(r"\d+", m.first.inner_text()).group())

            with run.step(f"style by {group_by}", required=False):
                _click_text(page, r"^uniform style$")
                page.wait_for_timeout(800)
                popup = page.get_by_text(re.compile(r"group places by", re.I)).first
                popup.wait_for(timeout=8000)
                # the dropdown inside the popup shows the same label as the link; it is the later one
                page.get_by_text(re.compile(r"^uniform style$", re.I)).last.click(timeout=8000)
                page.get_by_text(group_by, exact=True).last.click(timeout=8000)
                page.wait_for_timeout(800)
                page.keyboard.press("Escape")

            with run.step("verify places"):
                panel_text = page.inner_text("body")
                placed = [n for n in names if n in panel_text]
                missing = [n for n in names if n not in panel_text]

            map_url = page.url
            with run.step("verify map is saved", required=False):
                home = ctx.new_page()
                home.goto(MYMAPS, wait_until="domcontentloaded")
                home.get_by_text(title, exact=False).first.wait_for(timeout=20000)
                home.close()

            return {
                "ok": True, "map_url": map_url, "title": title,
                "rows": len(names), "placed": len(placed), "not_shown_reported": not_shown,
                "missing": missing, "warnings": run.warnings, "screenshots": str(run.dir),
                "next": "Open the Google Maps app with the same account → Saved (or You) → Maps.",
            }
        finally:
            with contextlib.suppress(Exception):
                ctx.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="Open Chrome and sign in to Google once")
    c = sub.add_parser("check", help="Check whether the saved session is signed in")
    c.add_argument("--show", action="store_true", help="Show the browser window")
    i = sub.add_parser("import", help="Create a My Map from a TripPilot CSV")
    i.add_argument("csv")
    i.add_argument("--title", default="TripPilot trip")
    i.add_argument("--headless", action="store_true", help="Hide the browser window")
    i.add_argument("--group-by", default="Category")
    ap.add_argument("--json", action="store_true", help="Print the result as JSON (for the app / MCP server)")
    args = ap.parse_args()

    try:
        if args.cmd == "login":
            result = login()
        elif args.cmd == "check":
            result = check(headless=not args.show)
        else:
            result = import_csv(args.csv, args.title, headless=args.headless, group_by=args.group_by)
    except (NotLoggedIn, StepFailed, ValueError, FileNotFoundError) as e:
        result = {"ok": False, "message": str(e)}
    except ImportError:
        result = {"ok": False, "message": "Playwright is not installed. Run: pip install -r requirements-local.txt "
                                          "&& playwright install chromium"}
    except Exception as e:  # browser crashed, no network, etc.
        result = {"ok": False, "message": f"{type(e).__name__}: {e}"}
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
