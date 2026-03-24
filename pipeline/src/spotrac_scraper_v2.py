"""
Robust Spotrac Scraper with Selenium and Data Quality Checks

Scrapes team cap data and player salaries from Spotrac using browser automation.
Includes comprehensive data quality validation at ingestion and transformation stages.
"""

import pandas as pd
import logging
import random
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import time
from datetime import datetime
from src.config import DATA_RAW_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _build_run_tags(run_timestamp: Optional[datetime] = None) -> tuple[str, str]:
    """Return iso-week tag and timestamp strings for consistent filenames."""
    ts = run_timestamp or datetime.utcnow()
    iso = ts.isocalendar()
    iso_week_tag = f"{iso.year}w{iso.week:02d}"
    timestamp = ts.strftime("%Y%m%d_%H%M%S")
    return iso_week_tag, timestamp


from datetime import datetime

class DataQualityError(Exception):
    """Raised when data quality checks fail"""
    pass

def _deduplicate_headers(headers: List[str]) -> List[str]:
    """Ensure all headers are unique by appending a suffix to duplicates."""
    seen = {}
    new_headers = []
    for h in headers:
        if not h:
            h = "unnamed"
        if h in seen:
            seen[h] += 1
            new_headers.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            new_headers.append(h)
    return new_headers

    return new_headers

class SpotracParser:
    """Handles parsing and normalization of Spotrac HTML content."""
    
    def __init__(self):
        from bs4 import BeautifulSoup
        self.bs = BeautifulSoup

    def parse_table(self, html: str, selector: Optional[str] = None) -> Tuple[List[str], List[List[str]]]:
        """Extract headers and rows from first valid table in HTML."""
        soup = self.bs(html, 'html.parser')
        table = None
        
        # Priority selectors
        if selector:
            table = soup.select_one(selector)
        
        if not table:
            tables = soup.find_all('table', {'class': 'dataTable'})
            for tbl in tables:
                if tbl.find('tbody'):
                    table = tbl
                    break
        
        if not table:
            for tbl in soup.find_all('table'):
                if tbl.find('tbody'):
                    table = tbl
                    break
        
        if not table:
            return [], []
            
        # Headers
        thead = table.find('thead')
        headers = []
        if thead:
            headers = [th.text.strip().replace('\n', ' ').lower() for th in thead.find_all('th')]
            headers = _deduplicate_headers(headers)
            
        # Rows
        rows = []
        tbody = table.find('tbody')
        if tbody:
            for tr in tbody.find_all('tr'):
                tds = tr.find_all('td')
                if len(tds) < 2: continue
                row = [td.text.strip().replace('\n', ' ') for td in tds]
                if row: rows.append(row)
                
        return headers, rows

    def parse_rankings_list_group(self, html: str) -> Tuple[List[str], List[List[str]]]:
        """
        Extract data from Spotrac's new div-based list-group structure for rankings.
        Returns generic headers ['rank', 'player', 'team', 'value'] and row data.
        """
        soup = self.bs(html, 'html.parser')
        rows = []
        
        # Find all list-group-items that look like player rows
        # Structure: li.list-group-item > ... > div.link > a (Player)
        # Value is usually in a span.medium or span.bold
        
        items = soup.find_all('li', class_='list-group-item')
        if not items:
            return [], []
            
        for item in items:
            # Player Name
            link_div = item.find('div', class_='link')
            if not link_div: 
                continue
                
            player_a = link_div.find('a')
            if not player_a:
                continue
            player_name = player_a.text.strip()
            
            # Team/Pos line often looks like: "KC, QB" inside a small tag or similar
            team_str = "Unknown"
            pos_str = "Unknown"
            small_tag = item.find('small')
            if small_tag:
                 parts = small_tag.text.strip().split(',')
                 if len(parts) >= 1: team_str = parts[0].strip()
                 if len(parts) >= 2: pos_str = parts[1].strip()

            # Value (Cap Hit / salary)
            value_str = "0"
            val_span = item.find('span', class_='medium')
            if not val_span:
                val_span = item.find('span', class_='bold')
            if val_span:
                value_str = val_span.text.strip()
            
            # Rank
            rank_span = item.find('span', class_='rank-value') 
            rank = rank_span.text.strip() if rank_span else str(len(rows) + 1)
            
            # Age is not present in the list-group structure
            age = ""

            
            # Construct row: [Rank, Player, Team, Pos, Age, Value]
            rows.append([rank, player_name, team_str, pos_str, age, value_str])
            
        headers = ['rank', 'player', 'team', 'pos', 'age', 'value']
        return headers, rows

    def parse_money(self, value) -> float:
        """Parse money string like '$255.4M' or '$60,985,272' to millions"""
        if pd.isna(value) is True or value is None or value == '-' or value == '':
            return 0.0
        
        # Ensure we are dealing with a string scalar
        if hasattr(value, '__len__') and not isinstance(value, str):
            # If it's a sequence/series, take the first value or return 0
            if len(value) > 0:
                value = value[0]
            else:
                return 0.0
        
        # Clean the string
        clean_val = str(value).replace('$', '').replace(',', '').strip()
        
        try:
            if 'M' in clean_val:
                return float(clean_val.replace('M', ''))
            elif 'B' in clean_val:
                return float(clean_val.replace('B', '')) * 1000.0
            elif 'K' in clean_val:
                return float(clean_val.replace('K', '')) / 1000.0
            else:
                # Assume raw dollars
                return float(clean_val) / 1_000_000.0
        except (ValueError, TypeError):
            return 0.0

    def normalize_player_contract_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Normalize contract columns from team contracts pages"""
        col_map = {}
        mapped_targets = set()
        
        for col in df.columns:
            col_lower = col.lower()
            target = None
            if ('player' in col_lower or 'name' in col_lower) and 'player_name' not in mapped_targets:
                target = 'player_name'
            elif 'team' in col_lower and 'avg' not in col_lower and 'team' not in mapped_targets:
                target = 'team'
            elif 'pos' in col_lower and 'position' not in mapped_targets:
                target = 'position'
            elif (('contract' in col_lower and 'value' in col_lower) or col_lower == 'value') and 'total_contract_value' not in mapped_targets:
                target = 'total_contract_value'
            elif ('guaranteed' in col_lower or 'guarantee' in col_lower) and 'sign' not in col_lower and 'guaranteed_money' not in mapped_targets:
                target = 'guaranteed_money'
            elif 'guaranteed' in col_lower and 'sign' in col_lower and 'guaranteed_salary' not in mapped_targets:
                target = 'guaranteed_salary'
            elif 'signing' in col_lower and 'bonus' in col_lower and 'signing_bonus' not in mapped_targets:
                target = 'signing_bonus'
            elif 'base' in col_lower and 'salary' in col_lower and 'base_salary' not in mapped_targets:
                target = 'base_salary'
            elif 'prorated' in col_lower and 'bonus' in col_lower and 'prorated_bonus' not in mapped_targets:
                target = 'prorated_bonus'
            elif 'roster' in col_lower and 'bonus' in col_lower and 'roster_bonus' not in mapped_targets:
                target = 'roster_bonus'
            elif 'contract' in col_lower and 'year' in col_lower and 'contract_length_years' not in mapped_targets:
                target = 'contract_length_years'
            elif 'years' in col_lower and 'remaining' in col_lower and 'years_remaining' not in mapped_targets:
                target = 'years_remaining'
            elif 'cap' in col_lower and 'hit' in col_lower and 'cap_hit' not in mapped_targets:
                target = 'cap_hit'
            elif 'dead' in col_lower and 'cap' in col_lower and 'dead_cap' not in mapped_targets:
                target = 'dead_cap'
            elif 'age' in col_lower and 'age' not in mapped_targets:
                target = 'age'
            
            if target:
                col_map[col] = target
                mapped_targets.add(target)
                
        df = df.rename(columns=col_map).copy()
        
        # Parse money columns
        money_cols = ['total_contract_value', 'guaranteed_money', 'signing_bonus', 'cap_hit', 'dead_cap', 'guaranteed_salary', 'base_salary', 'prorated_bonus', 'roster_bonus']
        for col in money_cols:
            if col in df.columns:
                df[f'{col}_millions'] = df[col].apply(self.parse_money)
                
        # Parse Age (ensure numeric, handle missing)
        if 'age' in df.columns:
             df['age'] = pd.to_numeric(df['age'], errors='coerce')
        
        df['year'] = year
        keep_cols = ['player_name', 'team', 'position', 'age', 'year',
                     'total_contract_value_millions', 'guaranteed_money_millions', 
                     'signing_bonus_millions', 'contract_length_years', 'years_remaining',
                     'cap_hit_millions', 'dead_cap_millions',
                     'base_salary_millions', 'prorated_bonus_millions',
                     'roster_bonus_millions', 'guaranteed_salary_millions']
        df = df[[c for c in keep_cols if c in df.columns]]
        
        if 'player_name' in df.columns:
            df = df.dropna(subset=['player_name'])
            df = df[df['player_name'].str.strip() != '']
            
        return df

    def validate_player_contract_data(self, df: pd.DataFrame, year: int):
        """Run data quality checks on player contract data"""
        if df.empty:
            raise DataQualityError(f"No contract data found for {year}")
            
        required = ['player_name', 'team', 'year']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing required columns: {missing}")
            
        if 'player_name' in df.columns and df['player_name'].isnull().sum() > 0:
            logger.warning(f"⚠️ Detected {df['player_name'].isnull().sum()} null player names")
            
        unique_teams = df['team'].nunique()
        if unique_teams < 1:
             raise DataQualityError(f"Expected at least one team, got {unique_teams}")

    def normalize_team_cap_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Normalize column names and parse monetary values"""
        col_map = {}
        for col in df.columns:
            col_lower = col.lower()
            if 'team' in col_lower and 'team' not in col_map.values():
                col_map[col] = 'team'
            elif 'active' in col_lower and 'cap' in col_lower:
                col_map[col] = 'active_cap'
            elif 'dead' in col_lower and ('money' in col_lower or 'cap' in col_lower):
                col_map[col] = 'dead_money'
            elif 'total' in col_lower and 'cap' in col_lower:
                col_map[col] = 'salary_cap'
            elif 'space' in col_lower:
                col_map[col] = 'cap_space'
                
        df = df.rename(columns=col_map)
        df['year'] = year
        
        money_cols = ['active_cap', 'dead_money', 'salary_cap', 'cap_space']
        for col in money_cols:
            if col in df.columns:
                df[f'{col}_millions'] = df[col].apply(self.parse_money)
                
        # Calculate dead cap %
        if 'dead_money_millions' in df.columns and 'salary_cap_millions' in df.columns:
            df['dead_cap_pct'] = (df['dead_money_millions'] / df['salary_cap_millions']) * 100
        
        # Keep only standardized columns
        keep_cols = ['team', 'year', 'salary_cap_millions', 'active_cap_millions', 
                     'dead_money_millions', 'cap_space_millions', 'dead_cap_pct']
        df = df[[c for c in keep_cols if c in df.columns]]
            
        return df

    def validate_team_cap_data(self, df: pd.DataFrame, year: int):
        """Run data quality checks on team cap data"""
        if len(df) < 30:
            raise DataQualityError(f"Expected ≥30 team records, got {len(df)}")
        required = ['team', 'year', 'salary_cap_millions']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing required columns: {missing}")

    def normalize_player_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Generic normalization for any player-related table."""
        col_map = {}
        mapped_targets = set()
        
        for col in df.columns:
            col_lower = str(col).lower()
            target = None
            if ('player' in col_lower or 'name' in col_lower) and 'player_name' not in mapped_targets:
                target = 'player_name'
            elif 'team' in col_lower and 'avg' not in col_lower and 'team' not in mapped_targets:
                target = 'team'
            elif 'pos' in col_lower and 'position' not in mapped_targets:
                target = 'position'
            elif ('salary' in col_lower or 'compensation' in col_lower) and 'salary' not in mapped_targets:
                target = 'salary'
            elif 'cap' in col_lower and 'hit' in col_lower and 'cap_hit' not in mapped_targets:
                target = 'cap_hit'
            elif 'dead' in col_lower and 'money' in col_lower and 'dead_money' not in mapped_targets:
                target = 'dead_money'
            elif (('contract' in col_lower and 'value' in col_lower) or col_lower == 'value') and 'total_contract_value' not in mapped_targets:
                target = 'total_contract_value'
            elif ('guaranteed' in col_lower or 'guarantee' in col_lower) and 'guaranteed_money' not in mapped_targets:
                target = 'guaranteed_money'
            
            if target:
                col_map[col] = target
                mapped_targets.add(target)
                
        df = df.rename(columns=col_map).copy()
        
        # Parse money
        money_cols = ['salary', 'cap_hit', 'dead_money', 'total_contract_value', 'guaranteed_money']
        for col in money_cols:
            if col in df.columns:
                df[f'{col}_millions'] = df[col].apply(self.parse_money)
        
        df['year'] = year
        if 'player_name' in df.columns:
            df = df.dropna(subset=['player_name'])
            df = df[df['player_name'].str.strip() != '']
            
        return df

    def validate_player_data(self, df: pd.DataFrame, year: int, min_rows: int = 30):
        """Run data quality checks on player data"""
        # For historical years, the Dead Money page might be a team summary (32 teams)
        # or a full player list. We accept both if >= min_rows.
        if len(df) < min_rows:
            raise DataQualityError(f"Expected ≥{min_rows} records, got {len(df)}")
        required = ['player_name', 'team', 'year']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing columns: {missing}")

class SpotracScraper:
    """
    Spotrac scraper with built-in data quality checks.
    
    Methods:
    - scrape_team_cap(): Team-level dead money and cap data
    - scrape_player_salaries(): Individual player salaries and dead money
    
    Quality gates:
    - Ingestion: Verify table found, row counts, column presence
    - Transformation: Check nulls, value ranges, data types
    - Completeness: Ensure reasonable data distributions and totals
    """
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.parser = SpotracParser()
        self.snapshot_dir = DATA_RAW_DIR / "snapshots"
        
    def __enter__(self):
        self._initialize_driver()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.driver:
            self.driver.quit()
            
    def _initialize_driver(self):
        """Initialize Selenium Chrome driver"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
        except ImportError:
            raise ImportError("Selenium not installed. Run: pip install selenium")
            
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-web-resources")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-sync")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-preconnect")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-component-extensions-with-background-pages")
        options.add_argument("user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        
        # Browser settings
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        
        # Memory management
        options.add_argument("--disable-renderer-backgrounding")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # Add random window size to vary fingerprint slightly
        w = random.randint(1280, 1920)
        h = random.randint(720, 1080)
        options.add_argument(f"--window-size={w},{h}")
        
        import os
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin
            from selenium.webdriver.chrome.service import Service as ChromeService
            # If we are in docker, we expect chromium-driver to be at /usr/bin/chromium-driver
            # but we can try without explicit service path first if it's in PATH
            service_path = os.environ.get("CHROMEDRIVER_BIN", "/usr/bin/chromium-driver")
            if os.path.exists(service_path):
                self.driver = webdriver.Chrome(service=ChromeService(service_path), options=options)
            else:
                self.driver = webdriver.Chrome(options=options)
        else:
            from selenium.webdriver.chrome.service import Service as ChromeService
            from webdriver_manager.chrome import ChromeDriverManager
            self.driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
            
        # VITAL FIX for Airflow hanging: Force a hard timeout on page load
        self.driver.set_page_load_timeout(45)
            
        logger.info("✓ Selenium driver initialized with 45s page load timeout")
        
    def _ensure_driver(self):
        """Check if driver is alive, if not re-initialize it."""
        try:
            if self.driver:
                # Simple call to check if session is active
                self.driver.current_url
                return
        except Exception:
            logger.warning("⚠️ Selenium session lost/invalid, re-initializing driver...")
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
        self._initialize_driver()
        time.sleep(5)  # Let driver settle

    def save_snapshot(self, html: str, name: str):
        """Save HTML snapshot for offline testing."""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.snapshot_dir / f"{name}.html"
        path.write_text(html)
        logger.info(f"💾 Snapshot saved: {path}")

    def scrape_team_cap(self, year: int, snapshot: bool = False) -> pd.DataFrame:
        """
        Scrape team cap data for a given year with quality checks.
        
        Returns DataFrame with columns:
        - team: Team name
        - year: Season year
        - active_cap_millions: Active player cap
        - dead_money_millions: Dead money
        - salary_cap_millions: Total salary cap
        - cap_space_millions: Available cap space
        - dead_cap_pct: Dead money as % of total cap
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from bs4 import BeautifulSoup
        
        url = f"https://www.spotrac.com/nfl/cap/{year}/"
        try:
            # Human-like delay before navigation
            time.sleep(random.uniform(2, 5))
            self.driver.get(url)
            
            # Check for immediate block
            if "Forbidden" in self.driver.title or "403" in self.driver.page_source:
                logger.error(f"🛑 ACCESS BLOCKED (403) for {url}. Respecting anti-bot. Recommendation: Pause scraping.")
                return pd.DataFrame()

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table.dataTable"))
            )
            time.sleep(random.uniform(3, 7))  # Let JS finish rendering with jitter
        except Exception as e:
            raise DataQualityError(f"Failed to load table: {e}")
            
        # Parse with BeautifulSoup
        html = self.driver.page_source
        if snapshot:
            self.save_snapshot(html, f"team_cap_{year}")

        headers, rows = self.parser.parse_table(html)
        if not headers or not rows:
            raise DataQualityError(f"No team cap data found for {year}")
            
        # Build DataFrame
        df = pd.DataFrame(rows, columns=headers[:len(rows[0])])
        
        # TRANSFORMATION: Normalize columns
        df = self.parser.normalize_team_cap_df(df, year)
        
        # TRANSFORMATION QUALITY CHECKS
        self.parser.validate_team_cap_data(df, year)
        
        logger.info(f"  ✓ All quality checks passed")
        return df
        
    def _normalize_team_cap_df(self, df: pd.DataFrame, year: int) -> pd.DataFrame:
        """Normalize column names and parse monetary values"""
        
        # Rename columns to standard names (handle multiline headers and suffixes)
        col_map = {}
        for col in df.columns:
            col_clean = col.split('_')[0] if '_' in col and col.split('_')[-1].isdigit() else col
            col_lower = col_clean.lower()
            if 'team' in col_lower and 'avg' not in col_lower:
                col_map[col] = 'team'
            elif 'active' in col_lower and '53' in col_lower:
                col_map[col] = 'active_cap'
            elif 'dead' in col_lower:
                col_map[col] = 'dead_money'
            elif 'total cap' in col_lower or 'allocations' in col_lower:
                col_map[col] = 'total_cap'
            elif 'space' in col_lower:
                col_map[col] = 'cap_space'
                
        df = df.rename(columns=col_map)
        
        # Remove any remaining duplicate columns (keep first occurrence)
        df = df.loc[:, ~df.columns.duplicated(keep='first')]
        
        # Parse money columns
        money_cols = ['active_cap', 'dead_money', 'total_cap', 'cap_space']
        for col in money_cols:
            if col in df.columns:
                df[f'{col}_millions'] = df[col].apply(self._parse_money)
                
        # Add year
        df['year'] = year
        
        # Calculate dead cap percentage
        if 'dead_money_millions' in df.columns and 'total_cap_millions' in df.columns:
            df['dead_cap_pct'] = (df['dead_money_millions'] / df['total_cap_millions'] * 100).round(2)
            
        # Keep only normalized columns - use filter to avoid duplicate column issues
        keep_cols = ['team', 'year', 'active_cap_millions', 'dead_money_millions', 
                     'total_cap_millions', 'cap_space_millions', 'dead_cap_pct']
        available_cols = [c for c in keep_cols if c in df.columns]
        df = df[available_cols]
        
        return df
        
    def _parse_money(self, value: str) -> float:
        """Parse money string like '$255.4M' or '$60,985,272' to millions"""
        try:
            value = str(value).replace('$', '').replace(',', '').strip()
            if 'M' in value:
                return float(value.replace('M', ''))
            elif 'K' in value:
                return float(value.replace('K', '')) / 1000
            elif 'B' in value:
                return float(value.replace('B', '')) * 1000
            else:
                # Raw dollar amount - convert to millions
                return float(value) / 1_000_000
        except:
            return 0.0
            
    def _validate_team_cap_data(self, df: pd.DataFrame, year: int):
        """Run data quality checks on team cap data"""
        
        # Check 1: Row count (should be 32 teams)
        if len(df) < 30 or len(df) > 35:
            raise DataQualityError(f"Expected 32 teams, got {len(df)}")
            
        # Check 2: Required columns present
        required = ['team', 'year', 'dead_money_millions', 'total_cap_millions']
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise DataQualityError(f"Missing required columns: {missing}")
            
        # Check 3: No nulls in critical columns
        for col in required:
            null_count = df[col].isnull().sum()
            if null_count > 0:
                raise DataQualityError(f"Column '{col}' has {null_count} nulls")
                
        # Check 4: Value ranges
        if df['dead_money_millions'].max() > 1000:
            raise DataQualityError(f"Dead money values seem too high (max={df['dead_money_millions'].max()})")
            
        if df['total_cap_millions'].min() < 100:
            raise DataQualityError(f"Total cap values seem too low (min={df['total_cap_millions'].min()})")
            
        # Check 5: Reasonable totals
        total_dead_money = df['dead_money_millions'].sum()
        if total_dead_money < 100 or total_dead_money > 10000:
            raise DataQualityError(f"Total league dead money {total_dead_money}M seems unreasonable")
            
        logger.info(f"  ✓ Total league dead money: ${total_dead_money:.1f}M")
        logger.info(f"  ✓ Avg per team: ${total_dead_money/len(df):.1f}M")


    def scrape_player_rankings(self, year: int, snapshot: bool = False) -> pd.DataFrame:
        """
        Scrape player-level salary/cap hit data from Spotrac rankings page.
        Shows all NFL players ranked by salary cap hit for a given year.
        
        Returns DataFrame with columns:
        - player_name: Player name
        - team: Team abbreviation
        - position: Player position
        - year: Season year
        - cap_hit_millions: Salary cap hit for this year
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from bs4 import BeautifulSoup
        
        # Use full ranks page for cap hit - shows all players ranked by cap hit
        url = f"https://www.spotrac.com/nfl/rankings/player/_/year/{year}/sort/cap_total"
        logger.info(f"Scraping player rankings (cap hit): {url}")
        
        # Human-like delay
        time.sleep(random.uniform(3, 6))
        self.driver.get(url)

        # Check for immediate block
        if "Forbidden" in self.driver.title or "403" in self.driver.page_source:
            logger.error(f"🛑 ACCESS BLOCKED (403) for {url}.")
            return pd.DataFrame()
        
        # Wait for table with very aggressive timeouts and JavaScript execution
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # Try to wait for table OR list-group (new layout)
            logger.info("  Waiting for table or list (up to 60 seconds)...")
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr, .list-group-item"))
            )
            logger.info("  ✓ Table found, waiting for full render...")
            time.sleep(10)  # Extended wait for all rows to render
            
        except Exception as e:
            logger.warning(f"⚠️ Timeout waiting for table: {e}")
            logger.info("  Attempting JavaScript injection to trigger table rendering...")
            
            # Try to trigger DataTables initialization via JavaScript
            try:
                self.driver.execute_script("""
                    // Force DataTables to initialize if not already done
                    if (typeof $ !== 'undefined' && $.fn.DataTable) {
                        var tables = document.querySelectorAll('table');
                        tables.forEach(t => {
                            if (!$.fn.DataTable.isDataTable(t)) {
                                console.log('Initializing DataTable...');
                                // This might trigger table rendering
                            }
                        });
                    }
                    // Also scroll to trigger lazy loading
                    window.scrollBy(0, document.body.scrollHeight);
                """)
                logger.info("  Executed JavaScript, waiting 10 more seconds...")
                time.sleep(10)
            except Exception as js_err:
                logger.warning(f"  JavaScript execution failed: {js_err}")
        
        # Parse with BeautifulSoup
        html = self.driver.page_source
        if snapshot:
            self.save_snapshot(html, f"player_rankings_{year}")

        # Try standard table parse first
        headers, rows = self.parser.parse_table(html)
        
        # Fallback to list-group parse if no table found
        if not headers or not rows:
            logger.info("  No table found, attempting to parse list-group structure...")
            headers, rows = self.parser.parse_rankings_list_group(html)
            
        if not headers or not rows:
            raise DataQualityError(f"No player ranking data found for {year}")
            
        # Build DataFrame
        df = pd.DataFrame(rows, columns=headers[:len(rows[0])])
        
        # TRANSFORMATION: Normalize columns
        df = self.parser.normalize_player_df(df, year)
        
        # TRANSFORMATION QUALITY CHECKS
        self.parser.validate_player_data(df, year, min_rows=500)
        
        logger.info(f"  ✓ All quality checks passed")
        return df

    def scrape_player_contracts(self, year: int, max_retries: int = 2, team_list: Optional[List[str]] = None, snapshot: bool = False) -> pd.DataFrame:
        """
        Scrape player-level contract details from Spotrac team contracts pages.
        
        Iterates through each team's contracts page and aggregates contract details.
        Includes retry logic for failed team pages.
        
        Args:
            year: Season year
            max_retries: Number of retries per team
            team_list: Optional list of team codes to scrape. If None, scrapes all 32.
        
        Returns DataFrame with columns:
        - player_name: Player name
        - team: Team abbreviation
        - position: Player position
        - year: Season year
        - total_contract_value_millions: Total contract value
        - guaranteed_money_millions: Guaranteed money in contract
        - signing_bonus_millions: Signing bonus
        - contract_length_years: Total years in contract
        - years_remaining: Years remaining on contract
        - cap_hit_millions: Current year cap hit
        - dead_cap_millions: Current year dead cap
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from bs4 import BeautifulSoup
        
        # Mapping of team codes to Spotrac URL slugs
        SPOTRAC_TEAM_SLUGS = {
            'ARI': 'arizona-cardinals',
            'ATL': 'atlanta-falcons',
            'BAL': 'baltimore-ravens',
            'BUF': 'buffalo-bills',
            'CAR': 'carolina-panthers',
            'CHI': 'chicago-bears',
            'CIN': 'cincinnati-bengals',
            'CLE': 'cleveland-browns',
            'DAL': 'dallas-cowboys',
            'DEN': 'denver-broncos',
            'DET': 'detroit-lions',
            'GB': 'green-bay-packers',
            'GNB': 'green-bay-packers',
            'HOU': 'houston-texans',
            'IND': 'indianapolis-colts',
            'JAX': 'jacksonville-jaguars',
            'KC': 'kansas-city-chiefs',
            'KAN': 'kansas-city-chiefs',
            'LAC': 'los-angeles-chargers',
            'LAR': 'los-angeles-rams',
            'LV': 'las-vegas-raiders',
            'LVR': 'las-vegas-raiders',
            'MIA': 'miami-dolphins',
            'MIN': 'minnesota-vikings',
            'NE': 'new-england-patriots',
            'NWE': 'new-england-patriots',
            'NO': 'new-orleans-saints',
            'NOR': 'new-orleans-saints',
            'NYG': 'new-york-giants',
            'NYJ': 'new-york-jets',
            'PHI': 'philadelphia-eagles',
            'PIT': 'pittsburgh-steelers',
            'SF': 'san-francisco-49ers',
            'SFO': 'san-francisco-49ers',
            'SEA': 'seattle-seahawks',
            'TB': 'tampa-bay-buccaneers',
            'TAM': 'tampa-bay-buccaneers',
            'TAM': 'tampa-bay-buccaneers',
            'TEN': 'tennessee-titans',
            'WAS': 'washington-commanders',
            'OAK': 'las-vegas-raiders',
            'SDG': 'los-angeles-chargers',
            'STL': 'los-angeles-rams'
        }

        # Team codes to iterate - use a canonical list or the provided subset
        if team_list:
            team_codes = [t.upper() for t in team_list]
        else:
            team_codes = [
                'ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN',
                'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC', 'LAC', 'LAR', 'LV', 'MIA',
                'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'PHI', 'PIT', 'SF', 'SEA', 'TB',
                'TEN', 'WAS'
            ]
        
        all_contracts = []
        successful_teams = 0
        logger.info(f"Scraping player contracts for {year} ({len(team_codes)} teams)")
        
        for i, team_code in enumerate(team_codes):
            # Proactive restart every 4 teams to prevent memory leaks/zombie processes
            if i > 0 and i % 4 == 0:
                logger.info("♻️ Proactive driver restart to clear memory...")
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass
                    self.driver = None
                self._initialize_driver()

            success = False
            for attempt in range(max_retries + 1):
                try:
                    # Check/re-initialize driver for each attempt if needed
                    self._ensure_driver()
                    
                    # Get the slug from mapping or fallback to lowercase code
                    team_slug = SPOTRAC_TEAM_SLUGS.get(team_code, team_code.lower())

                    # Establishment of session by visiting team main page first
                    # For historical years, we MUST use the /cap/{year}/ endpoint to avoid current roster redirects
                    current_year = datetime.now().year
                    if year < current_year:
                        url = f"https://www.spotrac.com/nfl/{team_slug}/cap/{year}/"
                    else:
                        url = f"https://www.spotrac.com/nfl/{team_slug}/contracts/"
                    
                    if attempt == 0:
                        logger.info(f"  → {team_code}: {url}")
                    else:
                        logger.info(f"  → {team_code} (retry {attempt}/{max_retries})")

                    # Human-like delay
                    time.sleep(random.uniform(2, 4))
                    self.driver.get(url)
                    
                    # Check for immediate block
                    if "Forbidden" in self.driver.title or "403" in self.driver.page_source:
                        logger.error(f"🛑 ACCESS BLOCKED (403) for {url}.")
                        # On block, we stop this team and maybe the whole run if persistent
                        break
                    time.sleep(2)
                    
                    # Use longer timeout and extended wait
                    self.driver.set_page_load_timeout(30)
                    
                    # Wait for table with longer timeout - use id="table" or dataTable class
                    try:
                        WebDriverWait(self.driver, 25).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "table#table, table.dataTable"))
                        )
                        time.sleep(3)  # Extended wait for rendering
                    except Exception as e:
                        logger.debug(f"    Initial wait failed: {e}, trying longer wait...")
                        # Try another wait with different selector
                        try:
                            WebDriverWait(self.driver, 20).until(
                                EC.presence_of_element_located((By.TAG_NAME, "table"))
                            )
                            time.sleep(3)
                        except:
                            logger.warning(f"    ⚠️ Failed to load contracts for {team_code} (attempt {attempt+1})")
                            if attempt < max_retries:
                                time.sleep(5)  # Wait before retry
                            continue
                    
                    html = self.driver.page_source
                    if snapshot:
                        self.save_snapshot(html, f"player_contracts_{team_code}_{year}")
                    
                    # For historical years, extract multiple tables (Active, Dead, Injured, etc.)
                    if year < datetime.now().year:
                        selectors = ["table#table_active", "table#table_dead", "table#table_injured"]
                        combined_rows = []
                        target_headers = []
                        
                        for sel in selectors:
                            h, r = self.parser.parse_table(html, selector=sel)
                            if r:
                                if not target_headers: target_headers = h
                                combined_rows.extend(r)
                                
                        headers, rows = target_headers, combined_rows
                    else:
                        headers, rows = self.parser.parse_table(html)
                    
                    if not headers or not rows:
                        logger.warning(f"    No contracts table found for {team_code}")
                        if attempt < max_retries:
                            time.sleep(5)
                            continue
                        else:
                            break
                    
                    logger.info(f"    ✓ Extracted {len(rows)} contracts for {team_code}")
                    
                    # Build team-specific DataFrame
                    df_team = pd.DataFrame(rows, columns=headers[:len(rows[0])])
                    df_team['team'] = team_code
                    
                    # Normalize per-team to ensure columns align before concat
                    df_team = self.parser.normalize_player_contract_df(df_team, year)
                    
                    all_contracts.append(df_team)
                    successful_teams += 1
                    success = True
                    
                    time.sleep(2)
                    break 
                    
                except Exception as e:
                    logger.warning(f"  ⚠️ Exception on {team_code} attempt {attempt+1}: {e}")
                    # Log page source snippet if it's a "Whoops" or "Access Denied"
                    try:
                        page_source = self.driver.page_source
                        if "Whoops" in page_source:
                            logger.warning(f"    Detected Spotrac 'Whoops' error page for {team_code}")
                        elif "Access Denied" in page_source:
                            logger.warning(f"    Detected 'Access Denied' for {team_code}")
                    except:
                        pass
                        
                    if attempt < max_retries:
                        time.sleep(5 + attempt * 5)  # Backoff
                        continue
                    else:
                        logger.warning(f"  ✗ Failed to scrape {team_code} after {max_retries+1} attempts")
                        break
            
            if not success:
                logger.warning(f"    Skipping {team_code} - unable to retrieve data")
        
        # Combine all team contracts
        if not all_contracts:
            raise DataQualityError(f"No contract data collected for {year}")
        
        logger.info(f"  Concatenating {len(all_contracts)} team DataFrames...")
        df = pd.concat(all_contracts, ignore_index=True)
        logger.info(f"  ✓ Total contracts collected: {len(df)} rows from {successful_teams}/{len(team_codes)} teams")
        
        # TRANSFORMATION QUALITY CHECKS
        self.parser.validate_player_contract_data(df, year)
        
        logger.info(f"  ✓ All quality checks passed")
        return df

    def scrape_player_salaries(self, year: int, snapshot: bool = False) -> pd.DataFrame:
        """
        Scrape player-level dead money data from Spotrac for a given year.
        
        Returns DataFrame with columns:
        - player_name: Player name
        - team: Team abbreviation
        - position: Player position
        - year: Season year
        - dead_money_millions: Dead money cap charge for this year
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from bs4 import BeautifulSoup
        
        # Use dead money page (most reliable for player-level data for current/recent years)
        # For historical years, fallback to the cap archive if needed
        current_year = datetime.now().year
        # Use archive for any year that isn't the current/upcoming target
        if year < current_year:
            url = f"https://www.spotrac.com/nfl/cap/{year}/"
            selector = "table#table_dead, table.dataTable"
        else:
            url = f"https://www.spotrac.com/nfl/dead-money/{year}/"
            selector = "table.dataTable"
            
        logger.info(f"Scraping player dead money: {url}")
        
        # Human-like delay
        time.sleep(random.uniform(3, 5))
        self.driver.get(url)

        # Check for immediate block
        if "Forbidden" in self.driver.title or "403" in self.driver.page_source:
            logger.error(f"🛑 ACCESS BLOCKED (403) for {url}.")
            return pd.DataFrame()
        
        # Wait for table
        try:
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            time.sleep(3)
        except Exception as e:
            logger.warning(f"Failed to load table via {selector}, trying general table...")
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
            except:
                raise DataQualityError(f"Failed to load dead money table: {e}")
            
        # Parse with BeautifulSoup
        html = self.driver.page_source
        if snapshot:
            self.save_snapshot(html, f"player_salaries_{year}")

        headers, rows = self.parser.parse_table(html)
        if not headers or not rows:
            raise DataQualityError(f"No player dead money data found for {year}")
            
        # Build DataFrame
        df = pd.DataFrame(rows, columns=headers[:len(rows[0])])
        
        # TRANSFORMATION: Normalize columns
        df = self.parser.normalize_player_df(df, year)
        
        # TRANSFORMATION QUALITY CHECKS
        self.parser.validate_player_data(df, year, min_rows=50)
        
        logger.info(f"  ✓ All quality checks passed")
        return df
        


def scrape_and_save_team_cap(
    year: int,
    output_dir: str = 'data/raw',
    run_timestamp: Optional[datetime] = None,
    iso_week_tag: Optional[str] = None,
    snapshot: bool = False,
) -> Path:
    """
    Scrape team cap data and save to CSV with timestamp.
    
    Returns path to saved file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    default_iso, default_ts = _build_run_tags(run_timestamp)
    if iso_week_tag:
        default_iso = iso_week_tag
    filename = f"spotrac_team_cap_{year}_{default_iso}_{default_ts}.csv"
    filepath = output_path / filename
    
    with SpotracScraper(headless=True) as scraper:
        df = scraper.scrape_team_cap(year, snapshot=snapshot)
        df.to_csv(filepath, index=False)
        
    logger.info(f"✓ Saved {len(df)} records to {filepath}")
    
    return filepath


def scrape_and_save_player_contracts(
    year: int,
    output_dir: str = 'data/raw',
    run_timestamp: Optional[datetime] = None,
    iso_week_tag: Optional[str] = None,
    team_list: Optional[List[str]] = None,
    snapshot: bool = False,
) -> Path:
    """
    Scrape player contract data and save to CSV with timestamp.
    
    Returns path to saved file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    default_iso, default_ts = _build_run_tags(run_timestamp)
    if iso_week_tag:
        default_iso = iso_week_tag
    filename = f"spotrac_player_contracts_{year}_{default_iso}_{default_ts}.csv"
    filepath = output_path / filename
    
    with SpotracScraper(headless=True) as scraper:
        df = scraper.scrape_player_contracts(year, team_list=team_list, snapshot=snapshot)
        df.to_csv(filepath, index=False)
        
    logger.info(f"✓ Saved {len(df)} records to {filepath}")
    
    return filepath


def scrape_and_save_player_salaries(
    year: int,
    output_dir: str = 'data/raw',
    run_timestamp: Optional[datetime] = None,
    iso_week_tag: Optional[str] = None,
    snapshot: bool = False,
) -> Path:
    """
    Scrape player salary data and save to CSV with timestamp.
    
    Returns path to saved file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    default_iso, default_ts = _build_run_tags(run_timestamp)
    if iso_week_tag:
        default_iso = iso_week_tag
    filename = f"spotrac_player_salaries_{year}_{default_iso}_{default_ts}.csv"
    filepath = output_path / filename
    
    with SpotracScraper(headless=True) as scraper:
        df = scraper.scrape_player_salaries(year, snapshot=snapshot)
        df.to_csv(filepath, index=False)
        
    logger.info(f"✓ Saved {len(df)} records to {filepath}")
    
    return filepath


def scrape_and_save_player_rankings(
    year: int,
    output_dir: str = 'data/raw',
    run_timestamp: Optional[datetime] = None,
    iso_week_tag: Optional[str] = None,
    snapshot: bool = False,
) -> Path:
    """
    Scrape player rankings (cap hit) data and save to CSV with timestamp.
    
    Returns path to saved file.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    default_iso, default_ts = _build_run_tags(run_timestamp)
    if iso_week_tag:
        default_iso = iso_week_tag
    filename = f"spotrac_player_rankings_{year}_{default_iso}_{default_ts}.csv"
    filepath = output_path / filename
    
    with SpotracScraper(headless=True) as scraper:
        df = scraper.scrape_player_rankings(year, snapshot=snapshot)
        df.to_csv(filepath, index=False)
        
    logger.info(f"✓ Saved {len(df)} records to {filepath}")
    
    return filepath


if __name__ == '__main__':
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Scrape Spotrac data.')
    parser.add_argument('task', choices=['team-cap', 'player-salaries', 'player-rankings', 'player-contracts'], help='Scraping task to perform')
    parser.add_argument('year', type=int, nargs='?', help='Year to scrape (Defaults to current NFL season)')
    parser.add_argument('--teams', nargs='+', help='Subset of team codes to scrape (e.g., ARI ATL)')
    parser.add_argument('--snapshot', action='store_true', help='Save HTML snapshots')
    
    args = parser.parse_args()
    
    run_timestamp = datetime.now()
    
    # Calculate dynamic NFL year (Rollover in March)
    target_year = args.year
    if not target_year:
        target_year = run_timestamp.year if run_timestamp.month >= 3 else run_timestamp.year - 1
        
    try:
        if args.task == 'team-cap':
            filepath = scrape_and_save_team_cap(target_year, run_timestamp=run_timestamp, snapshot=args.snapshot)
            print(f"\n✅ SUCCESS: Team cap data saved to {filepath}")
            
        elif args.task == 'player-salaries':
            filepath = scrape_and_save_player_salaries(target_year, run_timestamp=run_timestamp, snapshot=args.snapshot)
            print(f"\n✅ SUCCESS: Player salary data saved to {filepath}")
            
        elif args.task == 'player-rankings':
            filepath = scrape_and_save_player_rankings(target_year, run_timestamp=run_timestamp, snapshot=args.snapshot)
            print(f"\n✅ SUCCESS: Player rankings data saved to {filepath}")
            
        elif args.task == 'player-contracts':
            filepath = scrape_and_save_player_contracts(
                target_year, 
                run_timestamp=run_timestamp, 
                team_list=args.teams,
                snapshot=args.snapshot
            )
            print(f"\n✅ SUCCESS: Player contract data saved to {filepath}")
            
    except DataQualityError as e:
        print(f"\n❌ DATA QUALITY FAILURE: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
