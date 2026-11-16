import urllib.request
import re
from collections import Counter
from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = False

    def handle_data(self, data):
        if not self.skip:
            self.text.append(data)


def fetch_page(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extract_text(html):
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.text)


def word_frequency(text, top_n=10):
    words = re.findall(r"[a-zA-Z']+", text.lower())
    words = [w.strip("'") for w in words if len(w.strip("'")) > 1]
    return Counter(words).most_common(top_n)


if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    html = fetch_page(url)
    text = extract_text(html)
    top = word_frequency(text)
    for rank, (word, count) in enumerate(top, 1):
        print(f"{rank:2}. {word:<15} {count}")
