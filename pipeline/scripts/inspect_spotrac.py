import urllib.request
import sys

url = "https://www.spotrac.com/nfl/cap/2024/"
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Pragma": "no-cache",
    "Cache-Control": "no-cache",
}

try:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as response:
        html = response.read().decode("utf-8")
        print(f"Success! Length: {len(html)}")
        # Check for key data
        if "Dead Cap" in html or "dead" in html.lower():
            print("Found 'Dead' keyword.")
        else:
            print("keyword not found")

        # Save for inspection
        with open("spotrac_debug.html", "w") as f:
            f.write(html)
except Exception as e:
    print(f"Failed: {e}")
