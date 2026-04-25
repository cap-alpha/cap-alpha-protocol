#!/usr/bin/env python3
"""
Non-interactive weekly snapshot for Spotrac player rankings.
- Headless Firefox + Selenium
- Waits for page to render, scrolls, captures HTML+text
- Parses text to CSV (robust fallback)
- Retries, idempotent, logs summary
"""

import argparse
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

NAME_RE = re.compile(r"([A-Z][a-zA-Z.'\-]+(?:\s+[A-Z][a-zA-Z.'\-]+)+)")
CURR_RE = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
TEAM_RE = re.compile(r"\b([A-Z]{2,3})\b")
POS_RE = re.compile(
    r"\b(QB|WR|RB|TE|CB|S|FS|SS|LB|OLB|ILB|MLB|DE|DT|EDGE|OT|OG|C|DL|DB|K|P|LS)\b"
)


def parse_text_to_df(text: str, year: int) -> pd.DataFrame:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    rows = []
    for i, ln in enumerate(lines):
        if "$" not in ln:
            continue
        mcur = CURR_RE.search(ln)
        if not mcur:
            continue
        val = mcur.group(1)
        name = None
        team = None
        pos = None
        mname = NAME_RE.search(ln)
        if mname:
            name = mname.group(1)
        mteam = TEAM_RE.findall(ln)
        for t in mteam or []:
            if len(t) in (2, 3):
                team = t
                break
        mpos = POS_RE.search(ln)
        if mpos:
            pos = mpos.group(1)
        if not name:
            # fallback: previous lines
            for j in range(1, 4):
                if i - j < 0:
                    break
                prev = lines[i - j]
                mname2 = NAME_RE.search(prev)
                if mname2:
                    name = mname2.group(1)
                    break
                if not pos:
                    mpos2 = POS_RE.search(prev)
                    if mpos2:
                        pos = mpos2.group(1)
                if not team:
                    mteam2 = TEAM_RE.findall(prev)
                    for t in mteam2 or []:
                        if len(t) in (2, 3):
                            team = t
                            break
        if name:
            try:
                val_num = float("".join(ch for ch in val if ch.isdigit() or ch == "."))
            except Exception:
                val_num = None
            rows.append([name, team, pos, val_num, year])
    # dedupe by (name, value)
    seen = set()
    out = []
    for r in rows:
        k = (r[0], r[3])
        if k not in seen:
            seen.add(k)
            out.append(r)
    return pd.DataFrame(out, columns=["Player", "Team", "Position", "CapValue", "Year"])


def snapshot(
    year: int,
    outdir: Path,
    retries: int = 3,
    headless: bool = True,
    force: bool = False,
) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"player_rankings_{year}.csv"
    if csv_path.exists() and not force:
        log.info(f"CSV already exists, skipping: {csv_path}")
        return csv_path

    url = f"https://www.spotrac.com/nfl/rankings/player/_/year/{year}/sort/cap_total"

    # Prepare Firefox
    opts = Options()
    opts.headless = headless
    # reduce webdriver fingerprints
    opts.set_preference("dom.webdriver.enabled", False)
    opts.set_preference("useAutomationExtension", False)
    # random UA (may be ignored in recent Firefox; harmless)
    uas = [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    try:
        opts.set_preference("general.useragent.override", random.choice(uas))
    except Exception:
        pass

    last_err = None
    for attempt in range(1, retries + 1):
        driver = None
        try:
            driver = webdriver.Firefox(options=opts)
            log.info(f"Attempt {attempt}: GET {url}")
            driver.get(url)
            time.sleep(12 + attempt * 3)

            # try scrolls
            try:
                ActionChains(driver).send_keys(Keys.END).perform()
                time.sleep(2)
                ActionChains(driver).send_keys(Keys.HOME).perform()
                time.sleep(1)
                driver.execute_script(
                    "document.documentElement.scrollTop = document.documentElement.scrollHeight"
                )
                time.sleep(2)
            except Exception:
                pass

            html = driver.page_source
            try:
                main_text = (
                    driver.execute_script(
                        "return (document.querySelector('main')||document.body).innerText;"
                    )
                    or ""
                )
            except Exception:
                main_text = ""

            # dump artifacts
            (outdir / f"spotrac_{year}_raw.html").write_text(html)
            (outdir / f"spotrac_{year}_raw.txt").write_text(main_text)

            df = parse_text_to_df(main_text or html, year)
            log.info(f"Parsed rows: {len(df)}")
            if len(df) < 100:
                raise RuntimeError("Low row count; retrying")

            df.to_csv(csv_path, index=False)
            log.info(f"Saved CSV: {csv_path}")
            return csv_path
        except Exception as e:
            last_err = e
            log.warning(f"Attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

    raise RuntimeError(f"All attempts failed: {last_err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=datetime.now().year)
    ap.add_argument("--outdir", type=str, default="data/raw")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--no-headless", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out_path = snapshot(
        year=args.year,
        outdir=Path(args.outdir),
        retries=args.retries,
        headless=(not args.no_headless),
        force=args.force,
    )
    print(out_path)


if __name__ == "__main__":
    main()
