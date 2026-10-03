import json
from pathlib import Path


root = Path(__file__).resolve().parent.parent
notebook = json.loads((root / "Homework01.ipynb").read_text(encoding="utf-8"))


def set_code(index, source):
    cell = notebook["cells"][index]
    cell["source"] = source.strip("\n").splitlines(keepends=True)
    cell["execution_count"] = None
    cell["outputs"] = []


imports = "".join(notebook["cells"][4]["source"])
imports = imports.replace("your.name@innopolis.university", "ma.chegodaeva@innopolis.university")
set_code(4, imports)

set_code(6, r'''
import tempfile


class PoliteFetcher:
    """Downloads pages politely and keeps successful responses in a disk cache."""

    def __init__(self, cache_dir: str = "cache", user_agent: str = USER_AGENT,
                 delay: float = 0.0, timeout: float = 5.0) -> None:
        self.cache_dir = os.fspath(cache_dir)
        self.user_agent = user_agent
        self.delay = max(0.0, delay)
        self.timeout = timeout
        self.host_delays = {}
        self.last_request = {}
        os.makedirs(self.cache_dir, exist_ok=True)

    def cache_paths(self, url: str) -> Tuple[str, str]:
        """Hash the complete URL, including its query string."""
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return (os.path.join(self.cache_dir, key + ".body"),
                os.path.join(self.cache_dir, key + ".json"))

    def set_host_delay(self, netloc: str, seconds: float) -> None:
        host = netloc.lower()
        self.host_delays[host] = max(self.delay, self.host_delays.get(host, 0.0), seconds)

    def _request(self, url: str, stream: bool = False):
        # Follow redirects ourselves so that their requests also respect delays.
        headers = {"User-Agent": self.user_agent}
        if stream:
            headers["Accept-Encoding"] = "identity"
        for _ in range(31):
            host = urlsplit(url).netloc.lower()
            delay = self.host_delays.get(host, self.delay)
            if host in self.last_request:
                remaining = delay - (time.monotonic() - self.last_request[host])
                if remaining > 0:
                    time.sleep(remaining)
            self.last_request[host] = time.monotonic()
            response = requests.get(url, headers=headers, timeout=self.timeout,
                                    allow_redirects=False, stream=stream)
            if response.status_code not in (301, 302, 303, 307, 308) or not response.headers.get("Location"):
                return response
            url = urljoin(response.url, response.headers["Location"])
            response.close()
        raise requests.TooManyRedirects("Too many redirects")

    def _save_cache(self, result: Dict[str, Any]) -> None:
        body_path, meta_path = self.cache_paths(result["url"])
        metadata = {key: value for key, value in result.items() if key != "body"}
        # Each replacement is atomic; an incomplete cache entry is ignored on read.
        for destination, data in ((body_path, result["body"]),
                                  (meta_path, json.dumps(metadata).encode("utf-8"))):
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.cache_dir, delete=False) as handle:
                    temporary = handle.name
                    handle.write(data)
                os.replace(temporary, destination)
            finally:
                if temporary is not None and os.path.exists(temporary):
                    os.remove(temporary)

    def fetch(self, url: str) -> Dict[str, Any]:
        """Return url, final_url, status, content_type, body and from_cache."""
        result = {"url": url, "final_url": url, "status": None,
                  "content_type": "", "body": None, "from_cache": False}
        try:
            body_path, meta_path = self.cache_paths(url)
            try:
                with open(meta_path, encoding="utf-8") as handle:
                    metadata = json.load(handle)
                if metadata["status"] == 200 and metadata["url"] == url:
                    with open(body_path, "rb") as handle:
                        body = handle.read()
                    return {"url": url, "final_url": metadata["final_url"], "status": 200,
                            "content_type": metadata["content_type"], "body": body, "from_cache": True}
            except (OSError, ValueError, KeyError, TypeError):
                pass  # A missing or damaged cache entry can be downloaded again.

            with self._request(url) as response:
                result.update(final_url=response.url, status=response.status_code,
                              content_type=response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower(),
                              body=response.content if response.status_code == 200 else None)
            if result["status"] == 200:
                try:
                    self._save_cache(result)
                except OSError:
                    pass  # A cache write failure does not invalidate the response.
        except Exception:
            # The task requires fetch to return a record even for request failures.
            pass
        return result

    def download(self, url: str, path: str) -> Optional[str]:
        """Stream to a temporary file; publish only after checking length and hash."""
        temporary = None
        try:
            with self._request(url, stream=True) as response:
                if response.status_code != 200:
                    return None
                digest = hashlib.sha256()
                received = 0
                folder = os.path.dirname(os.path.abspath(path))
                with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
                    temporary = handle.name
                    for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            handle.write(chunk)
                            digest.update(chunk)
                            received += len(chunk)
                length = response.headers.get("Content-Length")
                checksum = response.headers.get("X-Checksum-SHA256")
                if length is not None and received != int(length):
                    return None
                if checksum is not None and digest.hexdigest() != checksum.strip().lower():
                    return None
            os.replace(temporary, path)
            temporary = None
            return digest.hexdigest()
        except Exception:
            return None
        finally:
            if temporary is not None:
                try:
                    os.remove(temporary)
                except OSError:
                    pass
''')

set_code(10, r'''
from urllib.parse import unquote_plus


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 section 5.2.4, preserving repeated and trailing slashes."""
    output = ""
    while path:
        if path.startswith("../"):
            path = path[3:]
        elif path.startswith("./"):
            path = path[2:]
        elif path.startswith("/./") or path == "/.":
            path = "/" + path[3:]
        elif path.startswith("/../") or path == "/..":
            path = "/" + path[4:]
            output = output.rsplit("/", 1)[0]
        elif path in (".", ".."):
            path = ""
        else:
            end = path.find("/", 1 if path.startswith("/") else 0)
            if end == -1:
                output += path
                path = ""
            else:
                output += path[:end]
                path = path[end:]
    return output


def normalize_url(url: str, base: Optional[str] = None) -> Optional[str]:
    """Resolve and canonicalize a URL, or return None if it is not http(s)."""
    try:
        url = url.strip()
        if base is not None:
            url = urljoin(base, url)
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        host = parts.hostname
        if scheme not in ("http", "https") or not host or any(c.isspace() for c in host):
            return None
        host = host.lower()
        port = parts.port  # Also validates malformed and out-of-range ports.
        if ":" in host:
            host = "[" + host + "]"
        if port is not None and (scheme, port) not in (("http", 80), ("https", 443)):
            host += ":" + str(port)
        parameters = []
        for parameter in parts.query.split("&"):
            name = unquote_plus(parameter.split("=", 1)[0]).lower()
            if parameter and not name.startswith("utm_"):
                parameters.append(parameter)
        path = _remove_dot_segments(parts.path) or "/"
        return urlunsplit((scheme, host, path, "&".join(parameters), ""))
    except Exception:
        return None


def _clean_text(element, separator: str = " ") -> str:
    return " ".join(element.get_text(separator).split()) if element is not None else ""


def _rel_values(element) -> Set[str]:
    values = element.get("rel", [])
    if isinstance(values, str):
        values = values.split()
    return {value.lower() for value in values}


def parse_page(html: bytes, page_url: str) -> Dict[str, Any]:
    """Return title, links, images, paragraphs, text, canonical and meta_robots."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove children before parents, since decompose also destroys descendants.
    for element in reversed(soup.select("script, style, noscript, template, [hidden]")):
        element.decompose()
    base_tag = soup.find("base", href=True)
    base = urljoin(page_url, base_tag["href"]) if base_tag else page_url
    links = []
    for anchor in soup.find_all("a", href=True):
        url = normalize_url(anchor["href"], base)
        if url is not None:
            links.append({"text": _clean_text(anchor), "url": url,
                          "nofollow": "nofollow" in _rel_values(anchor)})
    images = []
    seen_images = set()
    for element in soup.find_all("img"):
        source = element.get("data-src", "").strip() or element.get("src", "").strip()
        url = normalize_url(source, base) if source else None
        if url is not None and url not in seen_images:
            seen_images.add(url)
            images.append(url)
    body = soup.body if soup.body is not None else soup
    main = soup.find("main")
    paragraph_root = main if main is not None else body
    # Inline tags must not introduce spaces before punctuation in a paragraph.
    paragraphs = [_clean_text(p, separator="") for p in paragraph_root.find_all("p")]
    canonical = None
    for element in soup.find_all("link", href=True):
        if "canonical" in _rel_values(element):
            canonical = normalize_url(element["href"], base)
            break
    meta_robots = set()
    for element in soup.find_all("meta"):
        if element.get("name", "").lower() == "robots":
            meta_robots.update(directive.strip().lower()
                               for directive in element.get("content", "").split(",")
                               if directive.strip())
    return {"title": _clean_text(soup.title), "links": links, "images": images,
            "paragraphs": [p for p in paragraphs if p], "text": _clean_text(body),
            "canonical": canonical, "meta_robots": meta_robots}
''')

set_code(14, r'''
def split_sentences(text: str) -> List[str]:
    sentences = []
    start = 0
    # Keep punctuation and closing quotes/brackets in the preceding sentence.
    boundary = r"([.!?]+)[\"'\u201d\u2019\u00bb)\]}]*\s+"
    for match in re.finditer(boundary, text):
        if match.end() == len(text):
            continue
        following = text[match.end()]
        if not (following.isupper() or following.isdigit() or following in "\"'\u201c\u2018\u00ab([{"):
            continue
        if match.group(1) == ".":
            word_match = re.search(r"([^\W\d_]+(?:\.[^\W\d_]+)*)$", text[:match.start()])
            word = word_match.group(1).lower() if word_match else ""
            if word in ABBREVIATIONS or len(word) == 1:
                continue
        sentence = text[start:match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    remainder = text[start:].strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def tokenize(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", text.lower())


def top_terms(texts: List[str], n: int = 10) -> List[Tuple[str, int]]:
    counts = Counter(term for text in texts for term in tokenize(text)
                     if term not in STOPWORDS and not term.isdigit())
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max(0, n)]


def rank_sentences(question: str, sentences: List[str]) -> List[int]:
    """Indices of the matching sentences, best first."""
    query = sorted(set(tokenize(question)) - STOPWORDS)
    tokens = [tokenize(sentence) for sentence in sentences]
    terms = [set(sentence_tokens) for sentence_tokens in tokens]
    frequencies = Counter(term for sentence_terms in terms for term in sentence_terms)
    weights = {term: math.log((1 + len(sentences)) / (1 + frequencies[term])) + 1
               for term in query}
    scores = [sum(weights[term] for term in query if term in sentence_terms)
              for sentence_terms in terms]
    matches = [index for index, score in enumerate(scores) if score > 0]
    return sorted(matches, key=lambda index: (-scores[index], len(tokens[index]), index))


def precision_at_k(ranked: List[int], relevant: Set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    return sum(item in relevant for item in ranked[:k]) / k


def reciprocal_rank(ranked: List[int], relevant: Set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    for position, item in enumerate(ranked[:k], start=1):
        if item in relevant:
            return 1.0 / position
    return 0.0


def best_answer(question: str, pages: List[Dict[str, Any]]) -> Optional[Tuple[str, str]]:
    """Best sentence over all pages, as (sentence, page url)."""
    candidates = [(sentence, page["url"]) for page in pages
                  for paragraph in page["paragraphs"] for sentence in split_sentences(paragraph)]
    ranked = rank_sentences(question, [sentence for sentence, url in candidates])
    return candidates[ranked[0]] if ranked else None
''')

set_code(18, r'''
class Crawler:
    """Breadth-first crawler that yields one record per indexable HTML page."""

    def __init__(self, start_url: str, fetcher: "PoliteFetcher", max_pages: int = 20,
                 max_depth: int = 2, allowed_hosts: Optional[Set[str]] = None) -> None:
        self.errors: List[Tuple[str, Optional[int]]] = []
        self.blocked: List[str] = []
        self.start_url = normalize_url(start_url)
        self.fetcher = fetcher
        self.max_pages = max_pages
        self.max_depth = max_depth
        if allowed_hosts is None:
            self.allowed_hosts = {urlsplit(self.start_url).netloc} if self.start_url else set()
        else:
            self.allowed_hosts = {host.lower() for host in allowed_hosts}
        self.robots = {}

    def can_fetch(self, url: str) -> bool:
        """Load robots.txt once per host, before requesting any of its pages."""
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self.robots:
            robots_url = urlunsplit((parts.scheme, host, "/robots.txt", "", ""))
            response = self.fetcher.fetch(robots_url)
            parser = None
            if response["status"] == 200:
                parser = RobotFileParser()
                parser.parse((response["body"] or b"").decode("utf-8", errors="replace").splitlines())
                delay = parser.crawl_delay(self.fetcher.user_agent)
                if delay is not None:
                    self.fetcher.set_host_delay(host, delay)
            self.robots[host] = parser
        parser = self.robots[host]
        return parser is None or parser.can_fetch(self.fetcher.user_agent, url)

    def crawl(self) -> Iterator[Dict[str, Any]]:
        """Yield {"url", "depth", "title", "links"} for every indexable page."""
        if self.start_url is None or self.max_depth < 0:
            return
        queue = deque([(self.start_url, 0)])
        queued = {self.start_url}
        seen = set()
        attempts = 0
        while queue and attempts < self.max_pages:
            url, depth = queue.popleft()
            if url in seen or urlsplit(url).netloc not in self.allowed_hosts:
                continue
            seen.add(url)
            if not self.can_fetch(url):
                self.blocked.append(url)
                continue
            attempts += 1
            response = self.fetcher.fetch(url)
            if response["status"] != 200:
                self.errors.append((url, response["status"]))
                continue
            final_url = normalize_url(response["final_url"])
            if final_url is None or urlsplit(final_url).netloc not in self.allowed_hosts:
                continue
            if final_url != url and final_url in seen:
                continue
            seen.add(final_url)
            if response["content_type"] != "text/html":
                continue
            parsed = parse_page(response["body"], final_url)
            if "noindex" not in parsed["meta_robots"]:
                yield {"url": final_url, "depth": depth, "title": parsed["title"],
                       "links": [link["url"] for link in parsed["links"]]}
            if depth >= self.max_depth or "nofollow" in parsed["meta_robots"]:
                continue
            for link in parsed["links"]:
                target = link["url"]
                parts = urlsplit(target)
                if (link["nofollow"] or target in seen or target in queued
                        or parts.netloc not in self.allowed_hosts
                        or parts.path.lower().endswith(SKIP_EXTENSIONS)):
                    continue
                queue.append((target, depth + 1))
                queued.add(target)
''')

set_code(22, r'''
def parse_price(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = re.sub(r"[^0-9,.]", "", value)
        if "," in value and "." in value:
            value = value.replace(",", "")
        elif "," in value:
            if value.count(",") == 1 and len(value.rsplit(",", 1)[1]) == 2:
                value = value.replace(",", ".")
            else:
                value = value.replace(",", "")
    elif not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
        return round(number, 2) if math.isfinite(number) else None
    except (ValueError, OverflowError):
        return None


def parse_rating(value: Any) -> Optional[float]:
    """Convert a decimal rating or a fraction to the five-point scale."""
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
            if "/" in value:
                numerator, denominator = value.split("/", 1)
                value = 5 * float(numerator) / float(denominator)
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None


def parse_stock(value: Any) -> bool:
    """Accept positive quantities and the specified availability strings."""
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"yes", "in stock", "available"}:
            return True
        # API quantities can be strings too, as checked by the supplied grader.
        try:
            return float(value) > 0
        except ValueError:
            return False
    return False


def normalize_product(raw: Dict[str, Any]) -> Dict[str, Any]:
    raw_tags = raw.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split(",")
    tags = []
    for tag in raw_tags:
        tag = tag.strip().lower()
        if tag and tag not in tags:
            tags.append(tag)
    return {"id": int(raw["id"]), "name": " ".join(raw.get("title", "").split()),
            "price": parse_price(raw.get("price")), "rating": parse_rating(raw.get("rating")),
            "tags": tags, "in_stock": parse_stock(raw.get("stock"))}


def scrape_shop(shop_url: str, user_agent: str = USER_AGENT) -> List[Dict[str, Any]]:
    products = []
    seen_ids = set()
    with requests.Session() as session:
        session.headers.update({"User-Agent": user_agent})
        with session.get(shop_url, timeout=5) as response:
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            config = json.loads(soup.find("script", id="shop-config").string)
            next_url = urljoin(response.url, config["endpoint"])
        headers = {config["auth_header"]: config["token"]}
        while next_url is not None:
            with session.get(next_url, headers=headers, timeout=5) as response:
                if response.status_code == 429 and "Retry-After" in response.headers:
                    delay = max(0.0, float(response.headers["Retry-After"]))
                    response.close()
                    time.sleep(delay)
                    continue  # Retry the same URL with the same token.
                response.raise_for_status()
                data = response.json()
                for raw in data["items"]:
                    product_id = int(raw["id"])
                    if product_id not in seen_ids:
                        seen_ids.add(product_id)
                        products.append(normalize_product(raw))
                next_link = data["next"]
                next_url = urljoin(response.url, next_link) if next_link is not None else None
    return products


def filter_products(products: List[Dict[str, Any]], tag: Optional[str] = None,
                    max_price: Optional[float] = None, min_rating: Optional[float] = None,
                    in_stock_only: bool = False) -> List[int]:
    selected = []
    for product in products:
        if tag is not None and tag.strip().lower() not in product["tags"]:
            continue
        if max_price is not None and (product["price"] is None or product["price"] > max_price):
            continue
        if min_rating is not None and (product["rating"] is None or product["rating"] < min_rating):
            continue
        if in_stock_only and not product["in_stock"]:
            continue
        selected.append(product)
    selected.sort(key=lambda product: (
        -product["rating"] if product["rating"] is not None else math.inf,
        product["price"] if product["price"] is not None else math.inf,
        product["id"]))
    return [product["id"] for product in selected]
''')

set_code(26, '''
# Save the notebook before running this check: it grades the file on disk.
ir_sandbox.check_notebook("ma.chegodaeva@innopolis.university.ipynb")
''')

destination = root / "ma.chegodaeva@innopolis.university.ipynb"
destination.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(destination.name)
