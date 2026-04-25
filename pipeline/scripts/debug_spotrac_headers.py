import urllib.request
from html.parser import HTMLParser
import time


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_thead = False
        self.in_th = False
        self.headers = []
        self.current_data = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        if self.in_table and tag == "thead":
            self.in_thead = True
        if self.in_thead and tag == "th":
            self.in_th = True

    def handle_endtag(self, tag):
        if tag == "th":
            self.in_th = False
            if self.current_data:
                self.headers.append("".join(self.current_data).strip())
                self.current_data = []
        if tag == "thead":
            self.in_thead = False
        if tag == "table":
            self.in_table = False

    def handle_data(self, data):
        if self.in_th:
            self.current_data.append(data)


def debug_year(year):
    # url = f"https://www.spotrac.com/nfl/cap/_/year/{year}/sort/cap_dead"
    url = f"https://www.spotrac.com/nfl/cap/{year}/"
    print(f"Fetching {url}...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    )
    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8")

        parser = TableParser()
        parser.feed(html)
        print(f"Headers found for {year}:")
        print(parser.headers)

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    debug_year(2012)
