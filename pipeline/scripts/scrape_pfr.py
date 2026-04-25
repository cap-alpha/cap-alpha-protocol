import requests
import pandas as pd
from pathlib import Path
import time
import random
import logging
import argparse
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Spotrac Team Mapping
TEAM_MAP = {
    "ARI": "ARI",
    "ATL": "ATL",
    "BAL": "BAL",
    "BUF": "BUF",
    "CAR": "CAR",
    "CHI": "CHI",
    "CIN": "CIN",
    "CLE": "CLE",
    "DAL": "DAL",
    "DEN": "DEN",
    "DET": "DET",
    "GNB": "GB",
    "HOU": "HOU",
    "IND": "IND",
    "JAX": "JAX",
    "KAN": "KC",
    "LAC": "LAC",
    "LAR": "LAR",
    "LVR": "LV",
    "MIA": "MIA",
    "MIN": "MIN",
    "NWE": "NE",
    "NOR": "NO",
    "NYG": "NYG",
    "NYJ": "NYJ",
    "PHI": "PHI",
    "PIT": "PIT",
    "SFO": "SF",
    "SEA": "SEA",
    "TAM": "TB",
    "TEN": "TEN",
    "WAS": "WAS",
}


def scrape_pfr_gamelogs(year):
    # 1. Local File Check (Offline Mode)
    local_off_path = Path(f"data/raw/pfr/{year}/fantasy.html")
    html_content = None

    if local_off_path.exists():
        logger.info(f"Found local file: {local_off_path}. Loading offline data...")
        # Read file manually to handle encoding
        with open(local_off_path, "r", encoding="utf-8") as f:
            html_content = f.read()
    else:
        # 2. Web Scrape (Online Mode)
        url_off = f"https://www.pro-football-reference.com/years/{year}/fantasy.htm"
        logger.info(
            f"Local file not found ({local_off_path}). Attempting web scrape from: {url_off}..."
        )

        # Anti-Bot: Use Cloudscraper if available, else fall back to requests with modern headers
        try:
            import cloudscraper

            scraper = cloudscraper.create_scraper()
            logger.info("Using Cloudscraper to bypass anti-bot protection.")
        except ImportError:
            logger.warning(
                "Cloudscraper not found. Falling back to vanilla requests (likely to be blocked)."
            )
            scraper = requests.Session()

        # Manual Override: Use User-Provided Cookies/UA if available (Bypasses Cloudflare)
        manual_cookie = os.environ.get("PFR_COOKIE")
        manual_ua = os.environ.get("PFR_USER_AGENT")

        # Modern Headers (Chrome 122 on macOS)
        scraper.headers.update(
            {
                "User-Agent": manual_ua
                if manual_ua
                else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.pro-football-reference.com/",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        if manual_cookie:
            scraper.headers.update({"Cookie": manual_cookie})
            logger.info("Using Manual Cookie Injection for PFR.")

        try:
            # --- OFFENSE ---
            res_off = scraper.get(url_off)
            res_off.raise_for_status()
            html_content = res_off.text
        except Exception as e:
            logger.error(f"Failed to scrape PFR: {e}")
            raise

    # Parse HTML (works for both Local and Web)
    dfs_off = pd.read_html(html_content, header=1)

    # Robust Table Finding: Look for the table with 'Player' column
    df_off = None
    for df in dfs_off:
        if "Player" in df.columns:
            df_off = df
            break

    if df_off is None:
        logger.error("Could not find a table with 'Player' column in fantasy.html")
        logger.info(f"Tables found: {len(dfs_off)}")
        for i, df in enumerate(dfs_off):
            logger.info(f"Table {i} columns: {df.columns.tolist()}")
        raise ValueError("Invalid HTML structure: No fantasy table found.")

    df_off = df_off[df_off["Player"] != "Player"]

    # Normalize Offense
    df_final = pd.DataFrame()

    # Robust Column Finding
    def get_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return df[c]
        return pd.Series([None] * len(df))

    df_final["player_name"] = get_col(df_off, ["Player", "Player_Name"])
    df_final["team"] = get_col(df_off, ["Tm", "Team"])
    df_final["position"] = get_col(df_off, ["FantPos", "Pos"])
    df_final["year"] = year
    df_final["game_url"] = f"https://www.pro-football-reference.com/years/{year}/"

    # Numeric Stats (Offense)
    # Passing: Yds, TD
    # Rushing: Yds, TD
    # Receiving: Yds, TD

    df_final["Passing_Yds"] = pd.to_numeric(df_off.iloc[:, 9], errors="coerce").fillna(
        0
    )
    df_final["Passing_TD"] = pd.to_numeric(df_off.iloc[:, 10], errors="coerce").fillna(
        0
    )
    df_final["Rushing_Yds"] = pd.to_numeric(df_off.iloc[:, 13], errors="coerce").fillna(
        0
    )
    df_final["Rushing_TD"] = pd.to_numeric(df_off.iloc[:, 15], errors="coerce").fillna(
        0
    )
    df_final["Receiving_Yds"] = pd.to_numeric(
        df_off.iloc[:, 18], errors="coerce"
    ).fillna(0)
    df_final["Receiving_TD"] = pd.to_numeric(
        df_off.iloc[:, 20], errors="coerce"
    ).fillna(0)

    # --- DEFENSE ---
    local_def_path = Path(f"data/raw/pfr/{year}/defense.html")
    html_def_content = None

    if local_def_path.exists():
        logger.info(f"Found local file: {local_def_path}. Loading offline data...")
        with open(local_def_path, "r", encoding="utf-8") as f:
            html_def_content = f.read()
    else:
        url_def = f"https://www.pro-football-reference.com/years/{year}/defense.htm"
        logger.info(f"Scraping Defense: {url_def}...")
        time.sleep(random.uniform(5, 10))  # Increased delay for stealth

        # Re-use scraper from above if initialized
        try:
            if "scraper" not in locals():
                scraper = requests.Session()  # fallback

            res_def = scraper.get(url_def)
            res_def.raise_for_status()
            html_def_content = res_def.text
        except Exception as e:
            logger.error(f"Failed to scrape Defense: {e}")
            raise

    dfs_def = pd.read_html(html_def_content, header=1)

    # Robust Table Finding (Defense)
    df_def = None
    for df in dfs_def:
        if "Player" in df.columns:
            df_def = df
            break

    if df_def is None:
        logger.error("Could not find a table with 'Player' column in defense.html")
        raise ValueError("Invalid HTML structure: No defense table found.")

    df_def = df_def[df_def["Player"] != "Player"]

    logger.info(f"Defense Columns: {df_def.columns.tolist()}")
    logger.info(f"Defense Head: {df_def.head().to_string()}")

    df_d = pd.DataFrame()
    df_d["player_name"] = get_col(df_def, ["Player"])
    df_d["team"] = get_col(df_def, ["Tm", "Team"])

    # Stats
    df_d["Sacks"] = pd.to_numeric(
        get_col(df_def, ["Sk", "Sacks"]), errors="coerce"
    ).fillna(0)
    df_d["Interceptions"] = pd.to_numeric(
        get_col(df_def, ["Int", "Interceptions"]), errors="coerce"
    ).fillna(0)

    # Drop duplicates in defense (agg if needed? usually one row per player per year)
    df_d = df_d.groupby(["player_name", "team"]).sum().reset_index()

    # Map Team Abbrs in BOTH dfs
    df_final["team"] = df_final["team"].map(TEAM_MAP).fillna(df_final["team"])
    df_d["team"] = df_d["team"].map(TEAM_MAP).fillna(df_d["team"])

    df_final["team"] = df_final["team"].astype(str)
    df_d["team"] = df_d["team"].astype(str)

    # Merge keys
    df_final["merge_key"] = (
        df_final["player_name"]
        .astype(str)
        .str.replace("*", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip()
    )
    df_d["merge_key"] = (
        df_d["player_name"]
        .astype(str)
        .str.replace("*", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip()
    )

    df_merged = pd.merge(
        df_final,
        df_d[["merge_key", "team", "Sacks", "Interceptions"]],
        on=["merge_key", "team"],
        how="outer",
        suffixes=("", "_def"),
    )

    # Coalesce
    # If player was only in defense, they might have NaN for offense stats
    numeric_cols = [
        "Passing_Yds",
        "Passing_TD",
        "Rushing_Yds",
        "Rushing_TD",
        "Receiving_Yds",
        "Receiving_TD",
        "Sacks",
        "Interceptions",
    ]
    for col in numeric_cols:
        if col in df_merged.columns:
            df_merged[col] = df_merged[col].fillna(0)

    # Fill Metadata for defense-only players
    df_merged["player_name"] = df_merged["player_name"].fillna(
        df_merged["merge_key"]
    )  # simplify
    df_merged["year"] = df_merged["year"].fillna(year)
    df_merged["game_url"] = df_merged["game_url"].fillna(
        f"https://www.pro-football-reference.com/years/{year}/"
    )

    # Final cleanup
    df_out = df_merged.drop(columns=["merge_key"])

    # FIX: Apply cleaning to the final player_name column (remove *, +) because Spotrac keys don't have them
    df_out["player_name"] = (
        df_out["player_name"]
        .astype(str)
        .str.replace("*", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip()
    )

    # Filter out junk
    df_out = df_out.dropna(subset=["player_name"])

    # FIX: Deduplicate. If a player/team combo appears twice, keep the one with most games or just first.
    # This handles the case if outer join created ghosts or PFR has duplicates.
    df_out = df_out.drop_duplicates(subset=["player_name", "team"], keep="first")

    # Save
    output_dir = Path(f"data/raw/pfr/{year}")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"game_logs_{year}.csv"

    df_out.to_csv(output_path, index=False)
    logger.info(f"Saved {len(df_out)} rows (Merged Off+Def) to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    scrape_pfr_gamelogs(parser.parse_args().year)
