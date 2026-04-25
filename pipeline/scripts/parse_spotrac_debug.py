from html.parser import HTMLParser
import csv


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_thead = False
        self.in_tbody = False
        self.in_tr = False
        self.in_td = False
        self.in_th = False
        self.current_row = []
        self.tables = []
        self.current_table = []

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = []
        if self.in_table:
            if tag == "thead":
                self.in_thead = True
            if tag == "tbody":
                self.in_tbody = True
            if tag == "tr":
                self.in_tr = True
                self.current_row = []
            if tag in ["td", "th"]:
                self.in_td = True
                self.current_cell_text = ""

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
            self.tables.append(self.current_table)
        if self.in_table:
            if tag == "thead":
                self.in_thead = False
            if tag == "tbody":
                self.in_tbody = False
            if tag == "tr":
                self.in_tr = False
                if self.current_row:
                    self.current_table.append(self.current_row)
            if tag in ["td", "th"]:
                self.in_td = False
                self.current_row.append(self.current_cell_text.strip())

    def handle_data(self, data):
        if self.in_td:
            self.current_cell_text += data


parser = TableParser()
with open("spotrac_debug.html", "r") as f:
    html = f.read()
    parser.feed(html)

print(f"Found {len(parser.tables)} tables.")
for i, table in enumerate(parser.tables):
    print(f"--- Table {i} ---")
    # Print first few rows
    for row in table[:3]:
        print(row)
    print("...")
