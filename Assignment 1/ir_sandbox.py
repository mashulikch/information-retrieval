from __future__ import annotations

import argparse
import ast
import base64
import contextlib
import copy
import hashlib
import html as html_lib
import io
import json
import math
import os
import random
import re
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import traceback
import zlib
from collections import Counter, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit
from urllib.robotparser import RobotFileParser

VERSION = "2026.1"
BOT_NAME = "IRHomeworkBot"
GRADER_USER_AGENT = "IRHomeworkBot/1.0 (+grader@innopolis.university)"
PREFERRED_PORTS = (8765, 8766)
MIB = 1024 * 1024
DOWNLOAD_BLOCK = 256 * 1024
BIG_DOWNLOAD_SIZE = 32 * MIB
SMALL_DOWNLOAD_SIZE = 3 * MIB
BROKEN_DECLARED_SIZE = 6 * MIB
BROKEN_SENT_SIZE = 1 * MIB
TAMPERED_SIZE = 2 * MIB
MEMORY_LIMIT = 12 * MIB
EMAIL_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]*@innopolis\.university$")

# Modules a submission may import. Everything else is dropped by the grader.
ALLOWED_MODULES = {
    "__future__", "abc", "base64", "binascii", "bisect", "bs4", "codecs",
    "collections", "contextlib", "copy", "dataclasses", "datetime", "decimal",
    "email", "enum", "fractions", "functools", "gzip", "hashlib", "heapq",
    "html", "http", "io", "itertools", "json", "locale", "logging", "math",
    "mimetypes", "numbers", "operator", "os", "pathlib", "queue", "random",
    "re", "requests", "secrets", "shutil", "statistics", "string", "sys",
    "tempfile", "textwrap", "threading", "time", "types", "typing",
    "unicodedata", "urllib", "urllib3", "uuid", "warnings", "zlib",
}


def _clean_space(text: str) -> str:
    return " ".join(str(text).split())


def _tokens(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", str(text).lower())


def _short(value: Any, limit: int = 160) -> str:
    text = repr(value)
    if len(text) > limit:
        text = text[: limit - 15] + " ...(truncated)"
    return text

# ---------------------------------------------------------------------------
# Practice site content
#
# Paragraph strings use a tiny markup: [[link text|href]] is a link and
# [[link text|href|nofollow]] is a link with rel="nofollow". Host tokens such
# as {main} and {partner} are replaced with real addresses when a page is
# served.
# ---------------------------------------------------------------------------

PRACTICE_THEME: Dict[str, Any] = {
    "key": "practice",
    "museum": "Innopolis Museum of Natural History",
    "logo": "/files/logo.png",
    "nav": [
        ("/", "Home"),
        ("/halls/", "Halls"),
        ("/events/", "Events"),
        ("/shop/", "Shop"),
        ("/about/", "About us"),
    ],
    "footer": [
        ("p", "© 2026 Innopolis Museum of Natural History. Photos by the museum team."),
        ("p", "[[Contact|/about/#contact]] · [[info@imnh.example|mailto:info@imnh.example]] · [[Press kit (PDF)|/press/kit.pdf]]"),
    ],
    "head_style": ".qzstyle { color: #3a3a3a }",
    "body_end_script": "window.qzscript = 'page analytics'",
    "markers": ["qzscript", "qzstyle", "qznoscript", "qzhidden", "qztemplate", "qzcomment"],
    "hidden_targets": ["/halls/vault", "/tours/private", "/files/pixel.gif?page=ice-age"],
    "lazy_take": 2,
    "robots": (
        "# robots.txt for the Innopolis Museum of Natural History\n"
        "User-agent: *\n"
        "Disallow: /staff/\n"
        "Disallow: /search\n"
        "\n"
        "User-agent: IRHomeworkBot\n"
        "Disallow: /staff/\n"
        "Disallow: /archive/drafts/\n"
        "Disallow: /shop/cart\n"
    ),
    "redirects": {"/old/halls/rivers": "/halls/rivers"},
    "loop": ["/loop/a", "/loop/b"],
    "pages": {
        "/": {
            "title": "\n    Innopolis Museum of\n    Natural History\n  ",
            "h1": "Innopolis Museum of Natural History",
            "blocks": [
                ("p", "Welcome to a small museum with a big collection. We look after more than 12,400 objects, from river shells to a complete mammoth skeleton."),
                ("img", {"src": "/files/hero-mammoth.jpg", "alt": "The mammoth skeleton at night"}),
                ("p", "[[Featured this month: the Volga Rivers hall|/halls/rivers]]. It reopened after a long renovation and now has a sturgeon tank."),
                ("p", "[[About the museum|/about/?utm_source=home&utm_medium=banner]] · [[Plan a visit|#visit]] · [[Search the collection|/search?q=mammoth]]"),
                ("p", "[[Open the map|javascript:void(0)]] or [[call us|tel:+78435550199]] if you need directions."),
                ("p", "School computers can use our [[mirror site|{main_localhost}/about/]]. If you are in a hurry, [[see the skeleton|{main_upper}/halls/ice-age#skeleton]] first."),
                ("p", "We work with the [[Kazan Science Archive|{partner}/]] on field research. Check the [[  events page  |  /events/  ]] for lectures."),
                ("p#visit", "Opening hours: Tuesday to Sunday, 10:00 to 18:00. The museum is closed on Mondays."),
            ],
        },
        "/halls/": {
            "title": "Halls & galleries",
            "h1": "Our halls",
            "blocks": [
                ("p", "The museum has three permanent halls. Each one takes about forty minutes to see."),
                ("ul", [
                    "[[Ice Age|ice-age]]: mammoths, woolly rhinos and cave lions.",
                    "[[Volga Rivers|rivers?utm_campaign=autumn]]: fish, birds and the river delta.",
                    "[[Minerals|minerals]]: crystals from the Ural Mountains.",
                ]),
                ("img", {"src": "img/halls-map.png", "alt": "Map of the halls"}),
                ("p", "Bookmarked our old page? The [[old rivers page|/old/halls/rivers]] still works. You can also jump to the [[rivers hall map|rivers#map]]."),
                ("hidden", [("p", "qzhidden Coming soon: [[the vault|/halls/vault]].")]),
            ],
        },
        "/halls/ice-age": {
            "title": "Ice Age hall",
            "h1": "Ice Age hall",
            "blocks": [
                ("p", "The star of this hall is a mammoth skeleton found near Kazan in 1978. The skeleton is 3.2 m tall and about 45,000 years old."),
                ("figure", {"src": "/files/mammoth-skeleton.png", "alt": "Mammoth skeleton"}, "The skeleton after cleaning, photographed in 2025."),
                ("p", "Dr. Irina Petrova led the <<excavation>>. She still gives a talk here on the first Saturday of each month."),
                ("img", {"src": "/files/placeholder.gif", "data-src": "/files/woolly-rhino.png", "alt": "Woolly rhino"}),
                ("img", {"src": "/files/mammoth-skeleton.png", "alt": "Skeleton detail"}),
                ("img", {"src": "data:image/gif;base64,R0lGODlhAQABAAAAACw=", "alt": ""}),
                ("img", {"src": "  ../files/cave-lion.png ", "alt": "Cave lion"}),
                ("img", {"data-src": "   ", "src": "/files/tusk.jpg", "alt": "Tusk"}),
                ("p", "Related objects: [[the mammoth tusk|/exhibits/1]] and [[a cave lion skull|/exhibits/2]]."),
                ("noscript", [
                    ("style", ".qznoscript { display: none }"),
                    ("img", {"src": "/files/pixel.gif?page=ice-age", "alt": ""}),
                    ("p", "qznoscript Turn on JavaScript to rotate the 3D model."),
                ]),
                ("template", [("p", "qztemplate [[Private tour|/tours/private]]")]),
                ("script", "var qzscript = 'model viewer'"),
                ("comment", " qzcomment: the old banner was removed in May "),
                ("p_hidden", "qzhidden Staff note: move the rhino closer to the window."),
            ],
        },
        "/halls/rivers": {
            "title": "Volga Rivers hall",
            "base": "/collections/rivers/",
            "canonical": "/halls/rivers?utm_source=canonical",
            "h1": "Volga Rivers hall",
            "blocks": [
                ("p", "Our rivers hall follows the Volga from its source to the Caspian Sea. The sturgeon tank holds 12 fish, and the oldest one is 31 years old."),
                ("p", "Meet the [[Russian sturgeon|sturgeon]], or look at [[a map of the delta|delta-map|nofollow]]."),
                ("img", {"src": "img/sturgeon.png", "alt": "Sturgeon"}),
                ("p", "The hall also shows [[a paddle steamer model|../../exhibits/3]]."),
            ],
        },
        "/halls/minerals": {
            "title": "Minerals hall (closed for renovation)",
            "robots": "NOINDEX",
            "h1": "Minerals hall",
            "blocks": [
                ("p", "The minerals hall is closed for renovation until spring. Some crystals are on show in the [[Ice Age hall|/halls/ice-age]] for now."),
                ("p", "You can still read about [[the Ural emerald|/exhibits/4]] online."),
            ],
        },
        "/halls/vault": {
            "title": "The vault",
            "h1": "The vault",
            "blocks": [("p", "This page is not ready yet.")],
        },
        "/tours/private": {
            "title": "Private tours",
            "h1": "Private tours",
            "blocks": [("p", "Private tours are not available this year.")],
        },
        "/collections/rivers/sturgeon": {
            "title": "Russian sturgeon",
            "robots": "nofollow",
            "canonical_rel": "Canonical",
            "canonical": "sturgeon#top",
            "h1": "Russian sturgeon",
            "blocks": [
                ("p", "The Russian sturgeon can live for more than 50 years. Our largest fish is 1.6 m long."),
                ("p", "Sturgeon eggs are protected by law. Read the [[protection rules|/exhibits/5]]."),
            ],
        },
        "/collections/rivers/delta-map": {
            "title": "Volga delta map",
            "h1": "Volga delta map",
            "blocks": [("p", "The delta has more than 500 channels.")],
        },
        "/exhibits/1": {
            "title": "Mammoth tusk",
            "h1": "Mammoth tusk",
            "blocks": [
                ("p", "This tusk is 2.4 m long and weighs 47 kg. Students from St. Petersburg found it on a summer dig in 2003."),
                ("p", "Back to the [[Ice Age hall|/halls/ice-age]]. See also [[the cave lion skull|/exhibits/2]]."),
            ],
        },
        "/exhibits/2": {
            "title": "Cave lion skull",
            "h1": "Cave lion skull",
            "blocks": [
                ("p", "Cave lions were about 10% larger than modern lions! This skull came from a cave in the Ural Mountains."),
                ("p", "[[Mammoth tusk|/exhibits/1]] · [[Ice Age hall|/halls/ice-age]]"),
            ],
        },
        "/exhibits/3": {
            "title": "Paddle steamer model",
            "h1": "Paddle steamer model",
            "blocks": [
                ("p", "The model shows the steamer \"Volga\", built in 1911. It was made at a scale of 1:50 by Mr. Sorokin."),
                ("p", "[[Back to the rivers hall|/halls/rivers]] · [[Engine drawings|/exhibits/6|nofollow]]"),
            ],
        },
        "/exhibits/4": {
            "title": "Ural emerald",
            "h1": "Ural emerald",
            "blocks": [
                ("p", "The emerald weighs 2.3 kg, i.e. more than a bag of sugar. It was found in 1834."),
                ("p", "[[Minerals hall|/halls/minerals]]"),
            ],
        },
        "/exhibits/5": {
            "title": "Sturgeon protection rules",
            "h1": "Sturgeon protection rules",
            "blocks": [("p", "Catching sturgeon in the Volga has been banned since 2005.")],
        },
        "/exhibits/6": {
            "title": "Engine drawings",
            "h1": "Engine drawings",
            "blocks": [("p", "The drawings were scanned in 2021.")],
        },
        "/events/": {
            "title": "Events",
            "h1": "Events",
            "blocks": [
                ("p", "Lectures, workshops and night tours. Tickets for events are sold at the front desk."),
                ("ul", [
                    "[[Calendar|/calendar/2026-10]]",
                    "[[Mammoth talk with Dr. Petrova|/events/mammoth-talk]]",
                    "[[Museum gala 2019|/events/2019-gala]]",
                    "[[Live video from the sturgeon tank|/events/live-feed]]",
                    "[[Book a night tour|/loop/a]]",
                ]),
            ],
        },
        "/events/mammoth-talk": {
            "title": "Mammoth talk",
            "h1": "Mammoth talk",
            "blocks": [
                ("p", "Dr. Irina Petrova explains how the skeleton was found. The talk lasts about 50 minutes and is free for members."),
                ("p", "Meeting point: the [[Ice Age hall|/halls/ice-age]]."),
            ],
        },
        "/events/2019-gala": {
            "status": 404,
            "title": "Page not found",
            "h1": "Page not found",
            "blocks": [("p", "This event page was removed.")],
        },
        "/events/live-feed": {
            "status": 500,
            "title": "Server error",
            "h1": "Server error",
            "blocks": [("p", "The video server is not responding.")],
        },
        "/shop/": {
            "title": "Museum shop",
            "h1": "Museum shop",
            "blocks": [
                ("p", "Books, toys and posters from our collection. Every purchase supports the museum."),
                ("div", {"id": "catalog", "class": "product-grid"}, [("p", "Loading products...")]),
                ("noscript", [("p", "qznoscript Turn on JavaScript to see the products.")]),
                ("shop_config",),
                ("shop_script",),
                ("p", "[[Your cart|/shop/cart]]"),
            ],
        },
        "/shop/cart": {
            "title": "Your cart",
            "h1": "Your cart",
            "blocks": [("p", "Your cart is empty.")],
        },
        "/staff/": {
            "title": "Staff area",
            "h1": "Staff area",
            "blocks": [("p", "Staff only. Crawlers must not come here.")],
        },
        "/archive/drafts/": {
            "title": "Drafts",
            "h1": "Drafts",
            "blocks": [("p", "Unpublished drafts. Our robots.txt asks IRHomeworkBot to stay away.")],
        },
        "/about/": {
            "title": "About the museum",
            "h1": "About the museum",
            "blocks": [
                ("p", "The Innopolis Museum of Natural History opened its doors on 12 April 2014. It started with a gift of 800 fossils from a private collector."),
                ("p", "Read [[our history|history]] or go to the [[staff area|/staff/]]. Unfinished articles wait in the [[drafts archive|/archive/drafts/]]."),
                ("p", "A student ticket costs 150 rubles. Entry is free for children under 7."),
                ("quote", "“A museum is a conversation with the past.” (Prof. A. N. Volkov, founder)"),
                ("p", "[[Printable version|/print/about]] · [[Visitor numbers (JSON)|/api/export]] · [[Press kit|/press/kit.pdf]] · [[Write to us|mailto:info@imnh.example]] · [[Contact|#contact]]"),
            ],
        },
        "/about/history": {
            "title": "Our history",
            "h1": "Our history",
            "blocks": [
                ("p", "In 2014 the museum had only two rooms. The Ice Age hall was added in 2017, and the Volga Rivers hall followed in 2019."),
                ("p", "Mr. Volkov, the founder, collected fossils for 40 years. His first find was a shark tooth from the Kama river."),
                ("p", "Back to [[our halls|../halls/]]. Meet [[the founders|founders]]."),
            ],
        },
        "/about/founders": {
            "title": "The founders",
            "h1": "The founders",
            "blocks": [
                ("p", "The museum was founded by Prof. Andrei Volkov and his daughter Maria. The family still owns 30% of the collection."),
                ("p", "[[Our history|history]]"),
            ],
        },
        "/print/about": {
            "title": "About the museum (print version)",
            "chrome": False,
            "main": False,
            "h1": "About the museum",
            "blocks": [
                ("p", "The Innopolis Museum of Natural History opened its doors on 12 April 2014."),
                ("p", "Address: 1 Universitetskaya St., Innopolis. Phone: +7 843 555-01-99."),
            ],
        },
    },
    "calendar": {
        "prefix": "/calendar/",
        "title": "Calendar for {month} {year}",
        "blocks": [
            ("p", "Events in {month} {year}. Lectures take place every Saturday at 15:00."),
            ("p", "[[Previous month|{prev}]] · [[Next month|{next}]]"),
        ],
    },
    "search": {
        "path": "/search",
        "param": "q",
        "title": "Search results for “{q}”",
        "found": "{n} objects match your search.",
        "none": "No objects match your search.",
        "results": {
            "mammoth": ["[[Mammoth tusk|/exhibits/1]]", "[[Mammoth skeleton|/halls/ice-age#skeleton]]"],
            "sturgeon": ["[[Russian sturgeon|/collections/rivers/sturgeon]]"],
        },
        "again": "[[Run the search again|]]",
    },
    "export": {"path": "/api/export", "data": {"year": 2025, "visitors": 48210, "school_groups": 312}},
    "shop": {
        "api": "/api/v2/catalog",
        "header": "X-Shop-Token",
        "page_starts": [0, 3, 7, 11],
        "page_size": 4,
        "throttle_page": 3,
        "next_style": "query",
        "products": [
            {"id": 101, "title": "  Mammoth   plush toy ", "price": "1 299 ₽", "rating": "4.8/5", "tags": "Kids, Toys , kids", "stock": "in stock"},
            {"id": "102", "title": "Volga river map", "price": "₽450.00", "rating": 4.1, "tags": ["Posters", "Maps"], "stock": 3},
            {"id": 103, "title": "Fossil hunting kit", "price": "2\u00a0490,50 ₽", "rating": "9/10", "tags": "kids, science", "stock": "no"},
            {"id": 104, "title": "Museum mug", "price": 690, "rating": None, "tags": [], "stock": True},
            {"id": 105, "title": "Sturgeon fridge magnet", "price": "150 руб.", "rating": "4,5", "tags": "souvenirs", "stock": "Available"},
            {"id": 106, "title": "Ice Age picture book", "price": "890 RUB", "rating": 4.5, "tags": ["Books", "Kids"], "stock": 0},
            {"id": 107, "title": "Crystal growing set", "price": "on request", "rating": "", "tags": "science, KIDS", "stock": "yes"},
            {"id": 108, "title": "Paddle steamer model kit", "price": "₽3,150.00", "rating": 4.8, "tags": "models", "stock": "OUT OF STOCK"},
            {"id": "109", "title": "Cave lion T-shirt", "price": "1 190 ₽", "rating": "8/10", "tags": ["Clothes"], "stock": "2"},
            {"id": 110, "title": "Emerald keychain", "price": 350.0, "rating": 3.9, "tags": "souvenirs,  ", "stock": "no"},
            {"id": 111, "title": "Museum guidebook", "price": "600", "rating": "4.5 / 5", "tags": "books", "stock": "In Stock"},
            {"id": 112, "title": "Woolly rhino puzzle", "price": "990,00 ₽", "rating": 4.8, "tags": "kids,puzzles", "stock": 5},
            {"id": 113, "title": "Tote bag", "price": "₽ 450", "rating": None, "tags": None, "stock": "yes"},
            {"id": 114, "title": "Night tour gift card", "price": "2,000 RUB", "rating": "5/5", "tags": "gifts", "stock": True},
        ],
    },
    "partner": {
        "name": "Kazan Science Archive",
        "nav": [("/", "Archive home")],
        "footer": [("p", "Kazan Science Archive. The reading room is open on weekdays.")],
        "robots": "User-agent: *\nCrawl-delay: 1\nDisallow: /private/\n",
        "pages": {
            "/": {
                "title": "Kazan Science Archive",
                "h1": "Kazan Science Archive",
                "blocks": [
                    ("p", "We keep field notes and photographs from 1920 to 1990."),
                    ("ul", [
                        "[[Field notes|/objects/1]]",
                        "[[Photographs|/objects/2]]",
                        "[[Private notes|/private/notes]]",
                        "[[Halls of the Innopolis museum|{main}/halls/]]",
                    ]),
                ],
            },
            "/objects/1": {
                "title": "Field notes",
                "h1": "Field notes",
                "blocks": [("p", "The notes describe 140 digs along the Kama river."), ("p", "[[Photographs|/objects/2]]")],
            },
            "/objects/2": {
                "title": "Photographs",
                "h1": "Photographs",
                "blocks": [("p", "Most photographs are glass plates from the 1930s.")],
            },
            "/private/notes": {
                "title": "Private notes",
                "h1": "Private notes",
                "blocks": [("p", "Not for crawlers.")],
            },
        },
    },
    # URLs that the Task 1 tests use (paths on the main site)
    "fixtures": {
        "html_page": "/about/",
        "binary": "/files/mammoth-skeleton.png",
        "query_a": "/search?q=mammoth",
        "query_b": "/search?q=sturgeon",
        "cache_variants": ["/about/", "/about", "/About/", "/about/?lang=en", "/search?q=mammoth", "/search?q=sturgeon"],
        "missing": "/events/2019-gala",
        "broken": "/events/live-feed",
        "redirect": "/old/halls/rivers",
        "redirect_target": "/halls/rivers",
        "loop": "/loop/a",
        "delay_urls": ["/exhibits/1", "/exhibits/2", "/exhibits/3"],
        "partner_page": "/objects/1",
        "shop": "/shop/",
    },
    # Pages that the Task 2 tests parse. The value is the page_url passed to
    # parse_page (None means the page address itself).
    "parse_pages": {
        "/": None,
        "/halls/": None,
        "/halls/ice-age": None,
        "/halls/rivers": "/halls/rivers?utm_source=mail#intro",
        "/halls/minerals": None,
        "/collections/rivers/sturgeon": None,
        "/about/": None,
        "/print/about": None,
        "/search?q=mammoth": None,
    },
    "crawl": {
        "A": {"start": ["main", "/"], "max_pages": 30, "max_depth": 3},
        "B": {"start": ["main", "/"], "max_pages": 12, "max_depth": 3},
        "C": {"start": ["partner", "/"], "max_pages": 10, "max_depth": 1, "hosts": ["partner", "main"]},
        "D": {"start": ["main", "/events/"], "max_pages": 30, "max_depth": 1},
    },
    "crawl_roles": {
        "noindex_page": "/halls/minerals",
        "noindex_child": "/exhibits/4",
        "nofollow_page": "/collections/rivers/sturgeon",
        "nofollow_child": "/exhibits/5",
        "redirect_source": "/old/halls/rivers",
        "redirect_target": "/halls/rivers",
    },
    "qa": {
        "pages": ["/", "/about/", "/about/history", "/halls/ice-age", "/events/mammoth-talk", "/exhibits/1"],
        "questions": [
            "When did the museum open its doors?",
            "How tall is the mammoth skeleton?",
            "How much does a student ticket cost?",
            "Where can I park my bicycle?",
        ],
    },
}


PRACTICE_TABLES: Dict[str, Any] = {
    "normalize": [
        ["host", "HTTP://Example.COM/Path/Page", None, "http://example.com/Path/Page"],
        ["host", "https://example.com:443/a", None, "https://example.com/a"],
        ["host", "http://example.com:80/a", None, "http://example.com/a"],
        ["host", "http://example.com:8080/a", None, "http://example.com:8080/a"],
        ["host", "https://example.com:80/a", None, "https://example.com:80/a"],
        ["host", "http://user:secret@Example.com/a", None, "http://example.com/a"],
        ["fragment", "http://example.com", None, "http://example.com/"],
        ["fragment", "http://example.com/a#section-2", None, "http://example.com/a"],
        ["fragment", "  http://example.com/a/  ", None, "http://example.com/a/"],
        ["query", "http://example.com/a?utm_source=x&id=7", None, "http://example.com/a?id=7"],
        ["query", "http://example.com/a?b=2&a=1", None, "http://example.com/a?b=2&a=1"],
        ["query", "http://example.com/a?UTM_Medium=mail", None, "http://example.com/a"],
        ["query", "http://example.com/a?x=1&&y=2", None, "http://example.com/a?x=1&y=2"],
        ["query", "http://example.com/a?", None, "http://example.com/a"],
        ["dots", "http://example.com/a/b/../c", None, "http://example.com/a/c"],
        ["dots", "http://example.com/a/./b/.", None, "http://example.com/a/b/"],
        ["dots", "http://example.com/../../a", None, "http://example.com/a"],
        ["dots", "http://example.com/a/b/..", None, "http://example.com/a/"],
        ["relative", "../img/x.png", "http://example.com/a/b/page", "http://example.com/a/img/x.png"],
        ["relative", "?page=2", "http://example.com/list?page=1#top", "http://example.com/list?page=2"],
        ["relative", "//cdn.example.org/lib.js", "https://example.com/", "https://cdn.example.org/lib.js"],
        ["relative", "", "http://example.com/a?x=1#f", "http://example.com/a?x=1"],
        ["relative", "c", "http://example.com/a/b/", "http://example.com/a/b/c"],
        ["reject", "mailto:someone@example.com", None, None],
        ["reject", "javascript:void(0)", "http://example.com/", None],
        ["reject", "ftp://example.com/file", None, None],
        ["reject", "http://example.com:abc/", None, None],
        ["reject", "http:///no-host", None, None],
    ],
    "split": [
        ["basic", "The hall is open. It closes at six! Are you coming?", ["The hall is open.", "It closes at six!", "Are you coming?"]],
        ["basic", "  First line.\n\nSecond   line.  ", ["First line.", "Second   line."]],
        ["basic", "no terminator at the end", ["no terminator at the end"]],
        ["abbreviations", "Dr. Petrova met Mr. Smith. They talked.", ["Dr. Petrova met Mr. Smith.", "They talked."]],
        ["abbreviations", "The drawing by J. R. Tolkien was sold. Nobody knows the price.", ["The drawing by J. R. Tolkien was sold.", "Nobody knows the price."]],
        ["abbreviations", "Rocks, e.g. Granite, are heavy. Shells are not.", ["Rocks, e.g. Granite, are heavy.", "Shells are not."]],
        ["numbers_quotes", "The skeleton is 3.2 m tall. It is old.", ["The skeleton is 3.2 m tall.", "It is old."]],
        ["numbers_quotes", "She said \"Stop.\" Then she left.", ["She said \"Stop.\"", "Then she left."]],
        ["numbers_quotes", "(This part is quoted.) 2024 was a good year.", ["(This part is quoted.)", "2024 was a good year."]],
        ["edge", "Wait... what happened? Nothing.", ["Wait... what happened?", "Nothing."]],
        ["edge", "Really?! Yes.", ["Really?!", "Yes."]],
        ["edge", "", []],
        ["edge", "   ", []],
        ["edge", "the end. but lowercase follows", ["the end. but lowercase follows"]],
    ],
    "tokenize": [
        ["The Mammoth's tusk: 2.4 m!", ["the", "mammoth", "s", "tusk", "2", "4", "m"]],
        ["Kazán, КАЗАНЬ and Kazan_2", ["kazán", "казань", "and", "kazan", "2"]],
        ["", []],
        ["state-of-the-art   exhibits", ["state", "of", "the", "art", "exhibits"]],
    ],
    "top_terms": [
        [["The tusk and the skull.", "A tusk, a tooth, a TUSK!", "In 2003 the tusk was found."], 3],
        [["Rivers, rivers and more rivers.", "Fish live in rivers and lakes.", "Lakes 2 and 3."], 10],
        [[], 5],
    ],
    "rank": [
        ["order", "Where was the mammoth skeleton found?", [
            "The mammoth skeleton was found near Kazan.",
            "Mammoth tusks are heavy.",
            "The skeleton is tall.",
            "Nothing to see here.",
        ]],
        ["order", "How old is the oldest sturgeon?", [
            "Sturgeon can live for a long time.",
            "The oldest fish in the tank is 31 years old.",
            "Our oldest sturgeon is 31 years old.",
            "Old maps of the river are in the shop.",
        ]],
        ["ties", "cave lion", [
            "A cave lion skull from the Ural Mountains was found by students.",
            "The cave lion skull.",
            "Lion statues stand at the door.",
            "The cave was dark.",
        ]],
        ["empty", "Where is the?", ["The hall is here.", "Where is it?"]],
        ["empty", "mammoth", []],
    ],
    "metrics": [
        ["precision_at_k", [3, 1, 2], [1, 2], 2, 0.5],
        ["precision_at_k", [3], [3], 5, 0.2],
        ["precision_at_k", [5, 6, 7, 8], [], 3, 0.0],
        ["reciprocal_rank", [4, 2, 7], [7], 3, 1.0 / 3.0],
        ["reciprocal_rank", [4, 2, 7], [7], 2, 0.0],
        ["reciprocal_rank", [], [1], 3, 0.0],
        ["reciprocal_rank", [9, 1], [1, 9], 5, 1.0],
    ],
    "price": [
        [1299, 1299.0],
        [1299.5, 1299.5],
        ["1299", 1299.0],
        ["1 299 ₽", 1299.0],
        ["1\u00a0299,50 ₽", 1299.5],
        ["₽1,299.00", 1299.0],
        ["12,000 RUB", 12000.0],
        ["450 руб.", 450.0],
        ["on request", None],
        [None, None],
        [True, None],
        ["", None],
    ],
    "product": [
        [
            {"id": "7", "title": "  Toy   mammoth ", "price": "₽1,050.00", "rating": "9/10", "tags": "Kids, toys ,kids,", "stock": "In stock"},
            {"id": 7, "name": "Toy mammoth", "price": 1050.0, "rating": 4.5, "tags": ["kids", "toys"], "in_stock": True},
        ],
        [
            {"id": 8, "title": "Poster", "price": "on request", "rating": None, "tags": ["Art", "ART", " posters "], "stock": 0},
            {"id": 8, "name": "Poster", "price": None, "rating": None, "tags": ["art", "posters"], "in_stock": False},
        ],
        [
            {"id": 9, "title": "Mug", "price": 399, "rating": "4,2", "tags": None, "stock": "3"},
            {"id": 9, "name": "Mug", "price": 399.0, "rating": 4.2, "tags": [], "in_stock": True},
        ],
        [
            {"id": " 10 ", "title": "Magnet", "price": "99 руб.", "rating": "", "tags": "", "stock": "no"},
            {"id": 10, "name": "Magnet", "price": 99.0, "rating": None, "tags": [], "in_stock": False},
        ],
    ],
    "filters": [
        {"tag": "kids"},
        {"max_price": 1000, "in_stock_only": True},
        {"min_rating": 4.5, "tag": "Books"},
        {},
    ],
}

# ---------------------------------------------------------------------------
# Site model and HTML rendering
# ---------------------------------------------------------------------------

_MARKUP_RE = re.compile(r"\[\[(.*?)\]\]|<<(.*?)>>", re.S)
_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

_SHOP_SCRIPT = """
const config = JSON.parse(document.getElementById('shop-config').textContent)

function renderProducts(items) {
  const grid = document.getElementById('catalog')
  for (const item of items) {
    const card = document.createElement('article')
    card.textContent = item.title + ' ' + item.price
    grid.appendChild(card)
  }
}

async function loadProducts(url) {
  const response = await fetch(url, {headers: {[config.auth_header]: config.token}})
  if (response.status === 429) {
    const wait = Number(response.headers.get('Retry-After') || 1)
    setTimeout(() => loadProducts(url), wait * 1000)
    return
  }
  const data = await response.json()
  renderProducts(data.items)
  if (data.next) {
    loadProducts(new URL(data.next, url))
  }
}

loadProducts(new URL(config.endpoint, location.href))
"""

_GIF_BYTES = (b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00"
              b",\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;")


def _esc(text: Any) -> str:
    return html_lib.escape(str(text), quote=False)


def _attr(text: Any) -> str:
    return html_lib.escape(str(text), quote=True)


def _png_bytes(seed_text: str) -> bytes:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    width = height = 8
    pixel = bytes(digest[:3])
    raw = b"".join(b"\x00" + pixel * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    comment = b"Comment\x00" + seed_text.encode("utf-8")
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"tEXt", comment)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _jpeg_bytes(seed_text: str) -> bytes:
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + digest * 4 + b"\xff\xd9"


def _pdf_bytes(seed_text: str) -> bytes:
    body = ("%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
            "2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\n"
            "% " + seed_text + "\ntrailer << /Root 1 0 R >>\n%%EOF\n")
    return body.encode("utf-8")


def _stream_blocks(name: str, size: int) -> Iterable[bytes]:
    rnd = random.Random("ir-sandbox-download:" + name)
    remaining = size
    while remaining > 0:
        count = min(DOWNLOAD_BLOCK, remaining)
        yield rnd.randbytes(count)
        remaining -= count


_DIGEST_CACHE: Dict[Tuple[str, int], str] = {}
_DIGEST_LOCK = threading.Lock()


def _stream_digest(name: str, size: int) -> str:
    key = (name, size)
    with _DIGEST_LOCK:
        if key not in _DIGEST_CACHE:
            digest = hashlib.sha256()
            for block in _stream_blocks(name, size):
                digest.update(block)
            _DIGEST_CACHE[key] = digest.hexdigest()
        return _DIGEST_CACHE[key]


DOWNLOADS = {
    "/downloads/big.bin": {"size": BIG_DOWNLOAD_SIZE, "kind": "ok"},
    "/downloads/small.bin": {"size": SMALL_DOWNLOAD_SIZE, "kind": "ok"},
    "/downloads/broken.bin": {"size": BROKEN_DECLARED_SIZE, "kind": "broken"},
    "/downloads/tampered.bin": {"size": TAMPERED_SIZE, "kind": "tampered"},
}


class Site:
    """Everything that one version of the website serves."""

    def __init__(self, theme: Dict[str, Any], tables: Optional[Dict[str, Any]] = None) -> None:
        self.theme = theme
        self.tables = tables or {}
        self.key = theme["key"]
        self.partner = theme["partner"]

    # -- tokens -----------------------------------------------------------
    @staticmethod
    def fill(text: str, tokens: Dict[str, str]) -> str:
        for name, value in tokens.items():
            text = text.replace("{" + name + "}", value)
        return text

    # -- inline markup and blocks ----------------------------------------
    def inline(self, markup: str, tokens: Dict[str, str]) -> str:
        out: List[str] = []
        pos = 0
        for match in _MARKUP_RE.finditer(markup):
            out.append(_esc(markup[pos:match.start()]))
            if match.group(1) is not None:
                parts = match.group(1).split("|")
                label = parts[0]
                href = self.fill(parts[1] if len(parts) > 1 else "", tokens)
                rel = parts[2] if len(parts) > 2 else ""
                rel_attr = ' rel="%s"' % _attr(rel) if rel else ""
                out.append('<a href="%s"%s>%s</a>' % (_attr(href), rel_attr, _esc(label)))
            else:
                out.append("<em>%s</em>" % _esc(match.group(2)))
            pos = match.end()
        out.append(_esc(markup[pos:]))
        return "".join(out)

    @staticmethod
    def img_tag(attrs: Dict[str, str], tokens: Dict[str, str]) -> str:
        rendered = " ".join('%s="%s"' % (name, _attr(Site.fill(value, tokens))) for name, value in attrs.items())
        return "<img %s>" % rendered

    def blocks(self, blocks: List[Any], tokens: Dict[str, str], extra: Dict[str, Any], depth: int = 1) -> List[str]:
        pad = "  " * depth
        lines: List[str] = []
        for block in blocks:
            kind = block[0]
            if kind == "p":
                lines.append(pad + "<p>%s</p>" % self.inline(block[1], tokens))
            elif kind.startswith("p#"):
                lines.append(pad + '<p id="%s">%s</p>' % (_attr(kind[2:]), self.inline(block[1], tokens)))
            elif kind == "p_hidden":
                lines.append(pad + "<p hidden>%s</p>" % self.inline(block[1], tokens))
            elif kind == "h2":
                lines.append(pad + "<h2>%s</h2>" % _esc(block[1]))
            elif kind == "ul":
                lines.append(pad + "<ul>")
                for item in block[1]:
                    lines.append(pad + "  <li>%s</li>" % self.inline(item, tokens))
                lines.append(pad + "</ul>")
            elif kind == "img":
                lines.append(pad + self.img_tag(block[1], tokens))
            elif kind == "imglink":
                lines.append(pad + '<a href="%s">%s</a>' % (_attr(self.fill(block[1], tokens)), self.img_tag(block[2], tokens)))
            elif kind == "figure":
                lines.append(pad + "<figure>")
                lines.append(pad + "  " + self.img_tag(block[1], tokens))
                lines.append(pad + "  <figcaption>%s</figcaption>" % self.inline(block[2], tokens))
                lines.append(pad + "</figure>")
            elif kind == "quote":
                lines.append(pad + "<blockquote>")
                lines.append(pad + "  <p>%s</p>" % self.inline(block[1], tokens))
                lines.append(pad + "</blockquote>")
            elif kind in ("hidden", "noscript", "template"):
                opener = {"hidden": "<div hidden>", "noscript": "<noscript>", "template": "<template>"}[kind]
                closer = {"hidden": "</div>", "noscript": "</noscript>", "template": "</template>"}[kind]
                lines.append(pad + opener)
                lines.extend(self.blocks(block[1], tokens, extra, depth + 1))
                lines.append(pad + closer)
            elif kind == "div":
                attrs = " ".join('%s="%s"' % (k, _attr(v)) for k, v in block[1].items())
                lines.append(pad + "<div %s>" % attrs)
                lines.extend(self.blocks(block[2], tokens, extra, depth + 1))
                lines.append(pad + "</div>")
            elif kind == "script":
                lines.append(pad + "<script>%s</script>" % block[1])
            elif kind == "style":
                lines.append(pad + "<style>%s</style>" % block[1])
            elif kind == "comment":
                lines.append(pad + "<!--%s-->" % block[1])
            elif kind == "shop_config":
                shop = self.theme["shop"]
                config = {
                    "endpoint": shop["api"],
                    "auth_header": shop["header"],
                    "token": extra.get("token", ""),
                    "page_size": shop["page_size"],
                }
                lines.append(pad + '<script type="application/json" id="shop-config">%s</script>' % json.dumps(config))
            elif kind == "shop_script":
                lines.append(pad + "<script>%s</script>" % _SHOP_SCRIPT)
            else:
                raise ValueError("unknown block type %r" % (kind,))
        return lines

    # -- whole pages -------------------------------------------------------
    def render(self, page: Dict[str, Any], tokens: Dict[str, str], host: str = "main",
               extra: Optional[Dict[str, Any]] = None) -> bytes:
        extra = extra or {}
        conf = self.theme if host == "main" else self.partner
        chrome = page.get("chrome", True)
        lines = ["<!DOCTYPE html>", '<html lang="en">', "<head>", '  <meta charset="utf-8">']
        lines.append("  <title>%s</title>" % _esc(page.get("title", "")))
        lines.append('  <meta name="description" content="%s">' % _attr(page.get("h1", "")))
        if page.get("robots"):
            lines.append('  <meta name="robots" content="%s">' % _attr(page["robots"]))
        lines.append('  <link rel="stylesheet" href="/files/site.css">')
        if page.get("canonical"):
            rel = page.get("canonical_rel", "canonical")
            lines.append('  <link rel="%s" href="%s">' % (_attr(rel), _attr(self.fill(page["canonical"], tokens))))
        if page.get("base"):
            lines.append('  <base href="%s">' % _attr(self.fill(page["base"], tokens)))
        if host == "main" and conf.get("head_style"):
            lines.append("  <style>%s</style>" % conf["head_style"])
        lines.append("</head>")
        lines.append("<body>")
        if chrome:
            lines.append("<header>")
            if host == "main" and conf.get("logo"):
                lines.append('  <a class="logo" href="/"><img src="%s" alt="Logo"></a>' % _attr(conf["logo"]))
            lines.append("  <nav>")
            for href, label in conf["nav"]:
                lines.append('    <a href="%s">%s</a>' % (_attr(self.fill(href, tokens)), _esc(label)))
            lines.append("  </nav>")
            lines.append("</header>")
        container = "main" if page.get("main", True) else 'div class="content"'
        lines.append("<%s>" % container)
        if page.get("h1"):
            lines.append("  <h1>%s</h1>" % _esc(page["h1"]))
        lines.extend(self.blocks(page.get("blocks", []), tokens, extra))
        lines.append("</%s>" % container.split()[0])
        if chrome:
            lines.append("<footer>")
            lines.extend(self.blocks(conf.get("footer", []), tokens, extra))
            lines.append("</footer>")
            if host == "main" and conf.get("body_end_script"):
                lines.append("<script>%s</script>" % conf["body_end_script"])
        lines.append("</body>")
        lines.append("</html>")
        return ("\n".join(lines) + "\n").encode("utf-8")

    # -- generated pages ----------------------------------------------------
    def calendar_page(self, rest: str) -> Optional[Dict[str, Any]]:
        match = re.fullmatch(r"(\d{4})-(\d{2})", rest)
        if not match:
            return None
        year, month = int(match.group(1)), int(match.group(2))
        if not (1 <= month <= 12 and 1900 <= year <= 2999):
            return None
        prev_y, prev_m = (year, month - 1) if month > 1 else (year - 1, 12)
        next_y, next_m = (year, month + 1) if month < 12 else (year + 1, 1)
        cal = self.theme["calendar"]
        values = {
            "{month}": _MONTHS[month - 1],
            "{year}": str(year),
            "{prev}": "%s%04d-%02d" % (cal["prefix"], prev_y, prev_m),
            "{next}": "%s%04d-%02d" % (cal["prefix"], next_y, next_m),
        }

        def sub(text: str) -> str:
            for key, value in values.items():
                text = text.replace(key, value)
            return text

        title = sub(cal["title"])
        blocks = [(kind, sub(text)) for kind, text in cal["blocks"]]
        return {"title": title, "h1": title, "blocks": blocks}

    def search_page(self, query: str) -> Dict[str, Any]:
        search = self.theme["search"]
        params = parse_qs(query, keep_blank_values=True)
        term = params.get(search["param"], [""])[0]
        results = search["results"].get(term.strip().lower())
        blocks: List[Any] = []
        if results:
            blocks.append(("p", search["found"].replace("{n}", str(len(results)))))
            blocks.append(("ul", results))
        else:
            blocks.append(("p", search["none"]))
        blocks.append(("p", search["again"]))
        title = search["title"].replace("{q}", term)
        return {"title": title, "h1": title, "blocks": blocks}

    def binary_file(self, path: str) -> Optional[Tuple[str, bytes]]:
        lower = path.lower()
        if lower.endswith(".png"):
            return "image/png", _png_bytes(self.key + ":" + path)
        if lower.endswith(".gif"):
            return "image/gif", _GIF_BYTES
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            return "image/jpeg", _jpeg_bytes(self.key + ":" + path)
        if lower.endswith(".pdf"):
            return "application/pdf", _pdf_bytes(self.key + ":" + path)
        if lower.endswith(".css"):
            return "text/css; charset=utf-8", b"body { font-family: sans-serif }\n"
        return None

    def api_page(self, index: int) -> Tuple[List[Dict[str, Any]], Optional[int]]:
        shop = self.theme["shop"]
        starts = shop["page_starts"]
        start = starts[index]
        items = shop["products"][start:start + shop["page_size"]]
        next_index = index + 1 if index + 1 < len(starts) else None
        return items, next_index

    def api_next_link(self, index: int) -> str:
        shop = self.theme["shop"]
        cursor = base64.urlsafe_b64encode(("page-%d" % index).encode()).decode().rstrip("=")
        style = shop.get("next_style", "query")
        if style == "query":
            return "?cursor=" + cursor
        if style == "path":
            return shop["api"] + "?cursor=" + cursor
        return "{main}" + shop["api"] + "?cursor=" + cursor

    @staticmethod
    def decode_cursor(cursor: str) -> Optional[int]:
        if cursor == "":
            return 0
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            text = base64.urlsafe_b64decode(padded.encode()).decode()
        except (ValueError, UnicodeDecodeError):
            return None
        match = re.fullmatch(r"page-(\d+)", text)
        return int(match.group(1)) if match else None

# ---------------------------------------------------------------------------
# HTTP servers
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, status: int, content_type: str = "text/html; charset=utf-8", body: bytes = b"",
                 headers: Optional[Dict[str, str]] = None, length: Optional[int] = None,
                 stream: Optional[Iterable[bytes]] = None, close: bool = False) -> None:
        self.status = status
        self.content_type = content_type
        self.body = body
        self.headers = headers or {}
        self.length = length
        self.stream = stream
        self.close = close


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = os.name != "nt"

    def handle_error(self, request: Any, client_address: Any) -> None:
        return


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "IRSandbox/" + VERSION
    sys_version = ""
    disable_nagle_algorithm = True

    def log_message(self, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        self.server.sandbox._handle(self, self.server.host_label, "GET")

    def do_HEAD(self) -> None:
        self.server.sandbox._handle(self, self.server.host_label, "HEAD")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _prepare_environment() -> None:
    """Make sure requests never sends local traffic through a proxy."""
    for name in ("NO_PROXY", "no_proxy"):
        current = [part.strip() for part in os.environ.get(name, "").split(",") if part.strip()]
        for host in ("127.0.0.1", "localhost"):
            if host not in current:
                current.append(host)
        os.environ[name] = ",".join(current)


class Sandbox:
    """A running copy of the practice (or grading) website.

    Attributes you may find useful in the notebook:
        main      address of the museum site, for example http://127.0.0.1:8765
        partner   address of the partner archive site
        closed    an address where nothing is listening
    """

    def __init__(self, site: Site, ports: Tuple[int, int] = (0, 0)) -> None:
        _prepare_environment()
        self.site = site
        self.internal_token = secrets.token_hex(16)
        self.lock = threading.Lock()
        self.log: List[Dict[str, Any]] = []
        self.seq = 0
        self.shop_tokens: Dict[str, Dict[int, float]] = {}
        self.token_order: deque = deque()
        self.servers: Dict[str, _Server] = {}
        for label, port in zip(("main", "partner"), ports):
            server = self._bind(port)
            server.sandbox = self
            server.host_label = label
            self.servers[label] = server
        self.main_port = self.servers["main"].server_address[1]
        self.partner_port = self.servers["partner"].server_address[1]
        self.closed_port = _free_port()
        while self.closed_port in (self.main_port, self.partner_port):
            self.closed_port = _free_port()
        self.main = "http://127.0.0.1:%d" % self.main_port
        self.partner = "http://127.0.0.1:%d" % self.partner_port
        self.closed = "http://127.0.0.1:%d" % self.closed_port
        self.tokens = {
            "main_upper": "HTTP://127.0.0.1:%d" % self.main_port,
            "main_localhost": "http://LocalHost:%d" % self.main_port,
            "main": self.main,
            "partner": self.partner,
        }
        self.threads = []
        for server in self.servers.values():
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
            thread.start()
            self.threads.append(thread)

    @staticmethod
    def _bind(port: int) -> _Server:
        try:
            return _Server(("127.0.0.1", port), _Handler)
        except OSError:
            pass
        try:
            return _Server(("127.0.0.1", 0), _Handler)
        except OSError as exc:
            raise RuntimeError(
                "The practice site could not open a port on your machine (%s). Something is blocking local "
                "servers, usually a firewall or a security tool. Nothing here goes to the internet, the site "
                "only listens on 127.0.0.1, so allowing python to listen locally is safe." % exc)

    # -- helpers for the notebook ------------------------------------------
    def url(self, path: str = "/") -> str:
        """Full address of a page on the museum site."""
        return self.main + path

    def partner_url(self, path: str = "/") -> str:
        """Full address of a page on the partner site."""
        return self.partner + path

    def host_url(self, host: str, path: str) -> str:
        return (self.main if host == "main" else self.partner) + path

    def netloc(self, host: str = "main") -> str:
        return urlsplit(self.main if host == "main" else self.partner).netloc

    def alive(self) -> bool:
        return all(thread.is_alive() for thread in self.threads)

    def stop(self) -> None:
        for server in self.servers.values():
            server.shutdown()
            server.server_close()

    def info(self) -> None:
        lines = ["Practice site is running (ir_sandbox %s)." % VERSION]
        if self.main_port != PREFERRED_PORTS[0] or self.partner_port != PREFERRED_PORTS[1]:
            lines.append("  (ports %d and %d were busy, so free ones were picked. Nothing changes for you,"
                         % PREFERRED_PORTS)
            lines.append("   always build addresses with SITE.url(...) and never type a port by hand.)")
        lines += [
            "  museum site     %s/" % self.main,
            "  partner site    %s/" % self.partner,
            "  nothing here    %s/  (use it to test connection errors)" % self.closed,
            "Useful addresses for Task 1:",
            "  slow page       %s/_test/slow?seconds=3" % self.main,
            "  any status      %s/_test/status/404  (try 500, 503 and so on)" % self.main,
            "  your headers    %s/_test/headers" % self.main,
            "  downloads       %s/downloads/small.bin  big.bin  broken.bin  tampered.bin" % self.main,
            "Open the museum site in your browser to look around.",
            "SITE.requests() shows every request the site received.",
        ]
        print("\n".join(lines))

    # -- request log ---------------------------------------------------------
    def mark(self) -> int:
        with self.lock:
            return self.seq

    def requests(self, since: int = 0, host: Optional[str] = None) -> List[Dict[str, Any]]:
        """Requests received after the given mark, oldest first."""
        with self.lock:
            return [dict(entry) for entry in self.log
                    if entry["seq"] > since and (host is None or entry["host"] == host)]

    def clear_log(self) -> None:
        with self.lock:
            self.log.clear()

    def internal_get(self, url: str) -> Any:
        import requests
        session = requests.Session()
        session.trust_env = False
        try:
            return session.get(url, headers={"X-Sandbox-Internal": self.internal_token}, timeout=30)
        finally:
            session.close()

    def download_digest(self, path: str) -> str:
        name = path.rsplit("/", 1)[-1]
        return _stream_digest(name, DOWNLOADS[path]["size"])

    # -- request handling ------------------------------------------------------
    def _handle(self, handler: _Handler, host: str, method: str) -> None:
        headers = handler.headers
        internal = headers.get("X-Sandbox-Internal") == self.internal_token
        entry: Optional[Dict[str, Any]] = None
        if not internal:
            with self.lock:
                self.seq += 1
                entry = {
                    "seq": self.seq,
                    "time": time.perf_counter(),
                    "host": host,
                    "method": method,
                    "path": handler.path,
                    "user_agent": headers.get("User-Agent", ""),
                    "status": None,
                }
                self.log.append(entry)
                if len(self.log) > 20000:
                    del self.log[:5000]
        try:
            response = self._route(host, handler.path, headers, entry)
        except Exception as exc:
            response = _Response(500, "text/plain; charset=utf-8", ("sandbox error: %r" % (exc,)).encode())
        if entry is not None:
            entry["status"] = response.status
        self._send(handler, method, response)

    @staticmethod
    def _send(handler: _Handler, method: str, response: _Response) -> None:
        try:
            handler.send_response(response.status)
            if response.content_type:
                handler.send_header("Content-Type", response.content_type)
            length = response.length if response.length is not None else len(response.body)
            handler.send_header("Content-Length", str(length))
            for name, value in response.headers.items():
                handler.send_header(name, value)
            handler.end_headers()
            if method != "HEAD":
                if response.stream is not None:
                    for block in response.stream:
                        handler.wfile.write(block)
                else:
                    handler.wfile.write(response.body)
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, socket.timeout, OSError):
            handler.close_connection = True
        if response.close:
            handler.close_connection = True

    def _html(self, page: Dict[str, Any], host: str = "main", status: int = 200,
              extra: Optional[Dict[str, Any]] = None) -> _Response:
        body = self.site.render(page, self.tokens, host, extra)
        return _Response(status, "text/html; charset=utf-8", body)

    def _not_found(self, host: str) -> _Response:
        page = {"title": "Page not found", "h1": "Page not found",
                "blocks": [("p", "We could not find this page.")]}
        return self._html(page, host, 404)

    def _route(self, host: str, raw_path: str, headers: Any, entry: Optional[Dict[str, Any]]) -> _Response:
        parts = urlsplit(raw_path)
        path, query = parts.path, parts.query
        if host == "partner":
            return self._route_partner(path)
        theme = self.site.theme
        if path == "/robots.txt":
            return _Response(200, "text/plain; charset=utf-8", theme["robots"].encode("utf-8"))
        if path.startswith("/_test/"):
            return self._route_test(path, query, headers)
        if path in DOWNLOADS:
            return self._download(path)
        page = theme["pages"].get(path)
        if page is not None:
            extra: Dict[str, Any] = {}
            if any(block[0] == "shop_config" for block in page.get("blocks", [])):
                extra["token"] = self._new_token()
            return self._html(page, "main", page.get("status", 200), extra)
        if path in theme.get("redirects", {}):
            return _Response(301, "text/html; charset=utf-8", b"<p>Moved permanently</p>",
                             headers={"Location": theme["redirects"][path]})
        loop = theme.get("loop") or []
        if path in loop:
            target = loop[(loop.index(path) + 1) % len(loop)]
            return _Response(302, "text/html; charset=utf-8", b"<p>Found</p>", headers={"Location": target})
        calendar = theme["calendar"]
        if path.startswith(calendar["prefix"]):
            month_page = self.site.calendar_page(path[len(calendar["prefix"]):])
            if month_page is not None:
                return self._html(month_page)
        if path == theme["search"]["path"]:
            return self._html(self.site.search_page(query))
        if path == theme["export"]["path"]:
            return _Response(200, "application/json", json.dumps(theme["export"]["data"]).encode("utf-8"))
        if path == theme["shop"]["api"]:
            return self._api(query, headers, entry)
        binary = self.site.binary_file(path)
        if binary is not None:
            return _Response(200, binary[0], binary[1])
        return self._not_found("main")

    def _route_partner(self, path: str) -> _Response:
        partner = self.site.partner
        if path == "/robots.txt":
            return _Response(200, "text/plain; charset=utf-8", partner["robots"].encode("utf-8"))
        page = partner["pages"].get(path)
        if page is not None:
            return self._html(page, "partner", page.get("status", 200))
        return self._not_found("partner")

    def _route_test(self, path: str, query: str, headers: Any) -> _Response:
        params = parse_qs(query)
        if path == "/_test/slow":
            try:
                seconds = min(max(float(params.get("seconds", ["3"])[0]), 0.0), 10.0)
            except ValueError:
                seconds = 3.0
            time.sleep(seconds)
            page = {"title": "Slow page", "h1": "Slow page",
                    "blocks": [("p", "This page took %.1f seconds." % seconds)]}
            return self._html(page)
        match = re.fullmatch(r"/_test/status/(\d{3})", path)
        if match:
            code = int(match.group(1))
            if code == 200 or 400 <= code <= 599:
                page = {"title": "Status %d" % code, "h1": "Status %d" % code,
                        "blocks": [("p", "This page answers with status %d." % code)]}
                return self._html(page, status=code)
        if path == "/_test/headers":
            data = {name: value for name, value in headers.items()}
            return _Response(200, "application/json", json.dumps(data, indent=2).encode("utf-8"))
        return self._not_found("main")

    def _download(self, path: str) -> _Response:
        spec = DOWNLOADS[path]
        name = path.rsplit("/", 1)[-1]
        if spec["kind"] == "ok":
            headers = {"X-Checksum-SHA256": _stream_digest(name, spec["size"])}
            return _Response(200, "application/octet-stream", headers=headers, length=spec["size"],
                             stream=_stream_blocks(name, spec["size"]))
        if spec["kind"] == "tampered":
            headers = {"X-Checksum-SHA256": _stream_digest(name + ".original", spec["size"])}
            return _Response(200, "application/octet-stream", headers=headers, length=spec["size"],
                             stream=_stream_blocks(name, spec["size"]))
        return _Response(200, "application/octet-stream", length=spec["size"],
                         stream=_stream_blocks(name, BROKEN_SENT_SIZE), close=True)

    def _new_token(self) -> str:
        token = secrets.token_hex(8)
        with self.lock:
            self.shop_tokens[token] = {}
            self.token_order.append(token)
            while len(self.token_order) > 50:
                old = self.token_order.popleft()
                self.shop_tokens.pop(old, None)
        return token

    def _api(self, query: str, headers: Any, entry: Optional[Dict[str, Any]]) -> _Response:
        shop = self.site.theme["shop"]
        token = headers.get(shop["header"])
        cursor = parse_qs(query, keep_blank_values=True).get("cursor", [""])[0]
        info: Dict[str, Any] = {"cursor": cursor, "token_ok": False, "throttled": False}
        if entry is not None:
            entry["api"] = info
        with self.lock:
            valid = token is not None and token in self.shop_tokens
        if not valid:
            body = {"error": "missing or invalid token"}
            return _Response(401, "application/json", json.dumps(body).encode("utf-8"))
        info["token_ok"] = True
        index = Site.decode_cursor(cursor)
        if index is None or index >= len(shop["page_starts"]):
            return _Response(400, "application/json", json.dumps({"error": "bad cursor"}).encode("utf-8"))
        if index + 1 == shop["throttle_page"]:
            now = time.perf_counter()
            with self.lock:
                state = self.shop_tokens.get(token, {})
                first = state.get(index)
                if first is None:
                    state[index] = now
                    throttle = True
                else:
                    throttle = now - first < 0.9
            if throttle:
                info["throttled"] = True
                return _Response(429, "application/json", json.dumps({"error": "too many requests"}).encode("utf-8"),
                                 headers={"Retry-After": "1"})
        items, next_index = self.site.api_page(index)
        next_link = None
        if next_index is not None:
            next_link = Site.fill(self.site.api_next_link(next_index), self.tokens)
        data = {"items": items, "next": next_link}
        return _Response(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False).encode("utf-8"))


_ACTIVE: Optional[Sandbox] = None


def start(quiet: bool = False) -> Sandbox:
    """Start the practice site (or return the one that is already running)."""
    global _ACTIVE
    _prepare_environment()
    if _ACTIVE is None or not _ACTIVE.alive():
        _ACTIVE = Sandbox(Site(PRACTICE_THEME, PRACTICE_TABLES), PREFERRED_PORTS)
    if not quiet:
        _ACTIVE.info()
    return _ACTIVE


# ---------------------------------------------------------------------------
# Port independent expectations
# ---------------------------------------------------------------------------

def to_placeholders(obj: Any, sb: Sandbox) -> Any:
    rules = [
        (re.compile(r"127\.0\.0\.1:%d(?!\d)" % sb.main_port), "{MAIN}"),
        (re.compile(r"127\.0\.0\.1:%d(?!\d)" % sb.partner_port), "{PARTNER}"),
        (re.compile(r"127\.0\.0\.1:%d(?!\d)" % sb.closed_port), "{CLOSED}"),
        (re.compile(r"(?i)localhost:%d(?!\d)" % sb.main_port), "{MAIN_LOCALHOST}"),
    ]

    def convert(value: Any) -> Any:
        if isinstance(value, str):
            for pattern, replacement in rules:
                value = pattern.sub(replacement, value)
            return value
        if isinstance(value, (list, tuple)):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    return convert(obj)


def from_placeholders(obj: Any, sb: Sandbox) -> Any:
    values = {
        "{MAIN}": "127.0.0.1:%d" % sb.main_port,
        "{PARTNER}": "127.0.0.1:%d" % sb.partner_port,
        "{CLOSED}": "127.0.0.1:%d" % sb.closed_port,
        "{MAIN_LOCALHOST}": "localhost:%d" % sb.main_port,
    }

    def convert(value: Any) -> Any:
        if isinstance(value, str):
            for key, replacement in values.items():
                value = value.replace(key, replacement)
            return value
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {key: convert(item) for key, item in value.items()}
        return value

    return convert(obj)

# ---------------------------------------------------------------------------
# Reading a submitted notebook
#
# The grader keeps only imports of allowed modules, function definitions,
# class definitions and assignments of simple constants. Everything else at
# the top level of a cell (calls, prints, experiments, !pip lines) is ignored.
# ---------------------------------------------------------------------------

_SAFE_CALLS = {
    "set", "frozenset", "list", "tuple", "dict", "str", "int", "float", "bool",
    "sorted", "range", "len", "object", "defaultdict", "Counter", "OrderedDict",
    "namedtuple", "deque", "TypeVar", "NewType", "field", "re.compile",
    "re.escape", "collections.namedtuple", "collections.Counter",
    "collections.defaultdict", "collections.OrderedDict", "typing.TypeVar",
    "typing.NewType", "dataclasses.field", "str.maketrans", "os.path.join",
    "string.Template",
}
_SAFE_METHODS = {
    "split", "rsplit", "join", "lower", "upper", "strip", "lstrip", "rstrip",
    "replace", "format", "union", "difference", "intersection", "copy", "keys",
    "values", "items", "splitlines", "encode", "casefold", "title", "fromkeys",
}


def _dotted_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return base + "." + node.attr if base else None
    return None


def _root_name(node: ast.AST) -> Optional[str]:
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


class _SafetyChecker:
    def __init__(self, module_names: set) -> None:
        self.module_names = module_names

    def comprehension(self, generators: List[ast.comprehension]) -> bool:
        return all(self.expr(gen.iter) and all(self.expr(cond) for cond in gen.ifs) for gen in generators)

    def expr(self, node: Optional[ast.AST]) -> bool:
        if node is None:
            return True
        if isinstance(node, (ast.Constant, ast.Name)):
            return True
        if isinstance(node, ast.Attribute):
            return self.expr(node.value)
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return all(self.expr(item) for item in node.elts)
        if isinstance(node, ast.Dict):
            return all(self.expr(item) for item in node.keys) and all(self.expr(item) for item in node.values)
        if isinstance(node, ast.UnaryOp):
            return self.expr(node.operand)
        if isinstance(node, ast.BinOp):
            return self.expr(node.left) and self.expr(node.right)
        if isinstance(node, ast.BoolOp):
            return all(self.expr(item) for item in node.values)
        if isinstance(node, ast.Compare):
            return self.expr(node.left) and all(self.expr(item) for item in node.comparators)
        if isinstance(node, ast.IfExp):
            return self.expr(node.test) and self.expr(node.body) and self.expr(node.orelse)
        if isinstance(node, ast.Subscript):
            return self.expr(node.value) and self.expr(node.slice)
        if isinstance(node, ast.Slice):
            return self.expr(node.lower) and self.expr(node.upper) and self.expr(node.step)
        if isinstance(node, ast.JoinedStr):
            return all(self.expr(item) for item in node.values)
        if isinstance(node, ast.FormattedValue):
            return self.expr(node.value) and self.expr(node.format_spec)
        if isinstance(node, ast.Starred):
            return self.expr(node.value)
        if isinstance(node, ast.Lambda):
            return all(self.expr(item) for item in node.args.defaults + node.args.kw_defaults)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self.expr(node.elt) and self.comprehension(node.generators)
        if isinstance(node, ast.DictComp):
            return self.expr(node.key) and self.expr(node.value) and self.comprehension(node.generators)
        if isinstance(node, ast.Call):
            if not all(self.expr(arg) for arg in node.args):
                return False
            if not all(self.expr(keyword.value) for keyword in node.keywords):
                return False
            name = _dotted_name(node.func)
            if name in _SAFE_CALLS:
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr in _SAFE_METHODS:
                root = _root_name(node.func)
                if root is None or root not in self.module_names:
                    return self.expr(node.func.value)
            return False
        return False


def _import_roots(node: ast.AST) -> List[str]:
    if isinstance(node, ast.Import):
        return [alias.name.split(".")[0] for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        if node.level:
            return ["." * node.level + (node.module or "")]
        return [(node.module or "").split(".")[0]]
    return []


def _cell_source(cell: Dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        source = "".join(source)
    return str(source)


def _strip_magics(source: str) -> str:
    lines = []
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("!", "%")) or re.match(r"^\s*[\w.]+\s*=\s*[!%]", line):
            lines.append("")
        else:
            lines.append(line)
    return "\n".join(lines)


def extract_notebook(path: str) -> Tuple[str, List[str]]:
    """Return (python_code, notes) for a submitted notebook."""
    notes: List[str] = []
    try:
        with open(path, encoding="utf-8") as handle:
            notebook = json.load(handle)
        cells = notebook["cells"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError("this file is not a readable Jupyter notebook (%s)" % exc)

    module_names: set = set()
    checker = _SafetyChecker(module_names)
    future_lines: List[str] = []
    chunks: List[str] = []
    defined_in: Dict[str, List[int]] = defaultdict(list)
    dropped_assignments: Dict[str, Tuple[int, str]] = {}
    ignored_imports: List[str] = []
    code_cell_number = 0

    for cell in cells:
        if cell.get("cell_type") != "code":
            continue
        code_cell_number += 1
        source = _cell_source(cell)
        if not source.strip():
            continue
        if source.lstrip().startswith("%%"):
            notes.append("Code cell %d starts with a cell magic and was ignored." % code_cell_number)
            continue
        cleaned = _strip_magics(source)
        try:
            tree = ast.parse(cleaned)
        except SyntaxError as exc:
            notes.append("Code cell %d has a syntax error (line %s: %s) and was ignored completely."
                         % (code_cell_number, exc.lineno, exc.msg))
            continue
        kept: List[str] = []
        for node in tree.body:
            segment = ast.get_source_segment(cleaned, node) or ""
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                roots = _import_roots(node)
                bad = [root for root in roots if root not in ALLOWED_MODULES]
                if bad:
                    ignored_imports.extend(root for root in bad if root != "ir_sandbox")
                    continue
                if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                    future_lines.append(segment)
                    continue
                for alias in node.names:
                    module_names.add((alias.asname or alias.name).split(".")[0])
                kept.append(segment)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                decorators = ["@" + (ast.get_source_segment(cleaned, item) or "") for item in node.decorator_list]
                kept.append("\n".join(decorators + [segment]))
                defined_in[node.name].append(code_cell_number)
            elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                names = [t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name)]
                if value is None or checker.expr(value):
                    kept.append(segment)
                    for name in names:
                        defined_in[name].append(code_cell_number)
                else:
                    first_line = segment.splitlines()[0] if segment else ""
                    for name in names:
                        dropped_assignments[name] = (code_cell_number, first_line)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                continue
            else:
                continue
        if kept:
            chunks.append("# ---- code cell %d ----\n%s" % (code_cell_number, "\n\n".join(kept)))

    if ignored_imports:
        unique = sorted(set(ignored_imports))
        notes.append("These imports are not allowed and were ignored: %s." % ", ".join(unique))

    code = "\n\n\n".join(chunks)
    used_names = _global_names_used(code)
    for name, (cell_number, line) in sorted(dropped_assignments.items()):
        if name in used_names and name not in defined_in:
            notes.append("Your code uses %s, but its assignment in code cell %d (%s) runs code at import time, "
                         "so the grader ignored it. Create it inside a function or a class instead."
                         % (name, cell_number, line.strip()[:80]))
    for name, cells_list in sorted(defined_in.items()):
        if name in _ALL_REQUIRED_NAMES and len(set(cells_list)) > 1:
            notes.append("%s is defined in code cells %s. The grader uses the last definition."
                         % (name, ", ".join(str(n) for n in sorted(set(cells_list)))))

    header = ["# Code extracted by ir_sandbox %s from %s" % (VERSION, os.path.basename(path))]
    header.extend(future_lines)
    return "\n".join(header) + "\n\n" + code + "\n", notes


def _global_names_used(code: str) -> set:
    """Names the kept code looks up at module level (not locals, not attributes)."""
    import symtable
    used: set = set()
    try:
        table = symtable.symtable(code, "<submission>", "exec")
    except SyntaxError:
        return used

    def walk(scope: Any) -> None:
        is_module = str(scope.get_type()).lower().endswith("module")
        for symbol in scope.get_symbols():
            if not symbol.is_referenced():
                continue
            if is_module:
                if not (symbol.is_assigned() or symbol.is_imported()):
                    used.add(symbol.get_name())
            elif symbol.is_global():
                used.add(symbol.get_name())
        for child in scope.get_children():
            walk(child)

    walk(table)
    return used


def check_file_name(path: str) -> Optional[str]:
    """Return the student email from the file name, or None if the name is wrong."""
    name = os.path.basename(path)
    if not name.endswith(".ipynb"):
        return None
    email = name[: -len(".ipynb")]
    return email.lower() if EMAIL_RE.match(email.lower()) else None


def _load_module(path: str, name: str = "submission") -> Any:
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

TASK_TITLES = {
    1: "Polite fetcher",
    2: "URL normalization and page parsing",
    3: "Sentences, terms and ranking",
    4: "Crawler",
    5: "Shop behind a JSON API",
}
TASK_POINTS = {1: 20, 2: 20, 3: 15, 4: 30, 5: 15}
TASK_NAMES = {
    1: ["PoliteFetcher"],
    2: ["normalize_url", "parse_page"],
    3: ["split_sentences", "tokenize", "top_terms", "rank_sentences", "precision_at_k",
        "reciprocal_rank", "best_answer"],
    4: ["Crawler"],
    5: ["parse_price", "normalize_product", "scrape_shop", "filter_products"],
}
_ALL_REQUIRED_NAMES = {name for names in TASK_NAMES.values() for name in names}
_RESULT_KEYS = ("url", "final_url", "status", "content_type", "body", "from_cache")


class CheckFailed(Exception):
    def __init__(self, message: str, points: float = 0.0) -> None:
        super().__init__(message)
        self.points = points


class CheckTimeout(BaseException):
    pass


_CHECKS: Dict[int, List[Dict[str, Any]]] = defaultdict(list)


def _case(task: int, points: float, title: str, limit: float = 30) -> Callable:
    def decorator(func: Callable) -> Callable:
        _CHECKS[task].append({"name": func.__name__, "points": points, "title": title,
                              "func": func, "limit": limit})
        return func
    return decorator


def expect(condition: Any, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def _scaled(good: int, total: int, points: float, message: Optional[str]) -> float:
    if good == total:
        return points
    award = min(points - 1, int(points * good / max(1, total)))
    raise CheckFailed("%s (%d of %d cases correct)" % (message, good, total), max(0, award))


@contextlib.contextmanager
def _time_limit(seconds: Optional[float]) -> Iterator:
    usable = (seconds is not None and hasattr(signal, "setitimer")
              and threading.current_thread() is threading.main_thread())
    if not usable:
        yield
        return

    def on_alarm(signum: int, frame: Any) -> None:
        raise CheckTimeout()

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@contextlib.contextmanager
def _only_html_parser() -> Iterator:
    """The grader has no lxml or html5lib, so the tests hide them too."""
    try:
        from bs4.builder import HTMLParserTreeBuilder, builder_registry
    except Exception:
        yield
        return
    saved = list(builder_registry.builders)
    saved_features = {key: list(value) for key, value in builder_registry.builders_for_feature.items()}
    builder_registry.builders[:] = [b for b in saved if b is HTMLParserTreeBuilder]
    for key in list(builder_registry.builders_for_feature):
        builder_registry.builders_for_feature[key] = [b for b in saved_features[key] if b is HTMLParserTreeBuilder]
    try:
        yield
    finally:
        builder_registry.builders[:] = saved
        builder_registry.builders_for_feature.clear()
        builder_registry.builders_for_feature.update(saved_features)


class Context:
    def __init__(self, ns: Dict[str, Any], sb: Sandbox, expected: Dict[str, Any], workdir: str,
                 user_agent: str = GRADER_USER_AGENT, student_file: Optional[str] = None,
                 reference: Any = None) -> None:
        self.ns = ns
        self.sb = sb
        self.exp = expected
        self.theme = sb.site.theme
        self.tables = sb.site.tables
        self.workdir = workdir
        self.ua = user_agent
        self.student_file = student_file
        self.reference = reference
        self.cache: Dict[Any, Any] = {}
        self.counter = 0

    def need(self, name: str) -> Any:
        value = self.ns.get(name)
        if value is None:
            raise CheckFailed("%s is not defined (keep the exact name from the template)" % name)
        return value

    def new_dir(self, label: str) -> str:
        self.counter += 1
        path = os.path.join(self.workdir, "%02d-%s" % (self.counter, label))
        os.makedirs(path, exist_ok=True)
        return path

    def fixture(self, key: str) -> str:
        return self.sb.url(self.theme["fixtures"][key])

    def fetcher(self, label: str, **overrides: Any) -> Any:
        cls = self.need("PoliteFetcher")
        params = {"cache_dir": self.new_dir(label), "user_agent": self.ua, "delay": 0.0, "timeout": 5.0}
        params.update(overrides)
        return cls(**params)


def _is_student_frame(filename: str, ctx: Context) -> bool:
    path = os.path.abspath(filename)
    if ctx.student_file:
        return path == os.path.abspath(ctx.student_file)
    if path == os.path.abspath(__file__) or "site-packages" in path or "dist-packages" in path:
        return False
    return not path.startswith(os.path.abspath(os.path.dirname(os.__file__)))


def _describe_exception(exc: BaseException, ctx: Context) -> str:
    frames = [frame for frame in traceback.extract_tb(exc.__traceback__) if _is_student_frame(frame.filename, ctx)]
    where = ""
    if frames:
        frame = frames[-1]
        where = " (in %s" % frame.name
        if frame.line:
            where += ", at the line: %s" % frame.line.strip()[:100]
        where += ")"
    message = "your code raised %s: %s%s" % (type(exc).__name__, str(exc)[:200], where)
    if type(exc).__name__ == "FeatureNotFound":
        message += ". Use BeautifulSoup(html, 'html.parser'), other parsers are not installed on the grader"
    return message


def _attempt(ctx: Context, func: Callable) -> Tuple[bool, str]:
    try:
        func()
        return True, ""
    except CheckFailed as exc:
        return False, str(exc)
    except CheckTimeout:
        raise
    except Exception as exc:
        return False, _describe_exception(exc, ctx)


def _check_result(result: Any) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise CheckFailed("fetch must return a dict, it returned %s" % type(result).__name__)
    missing = [key for key in _RESULT_KEYS if key not in result]
    if missing:
        raise CheckFailed("the dict returned by fetch has no key(s) %s" % ", ".join(missing))
    return result


def _file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(MIB), b""):
            digest.update(block)
    return digest.hexdigest()


# -- Task 1 ------------------------------------------------------------------

@_case(1, 2, "fetch returns an HTML page with all fields")
def t1_page(ctx: Context) -> None:
    url = ctx.fixture("html_page")
    expected = ctx.sb.internal_get(url).content
    result = _check_result(ctx.fetcher("t1-page").fetch(url))
    expect(result["status"] == 200, "status should be 200, got %r" % (result["status"],))
    expect(isinstance(result["body"], bytes), "body should be bytes, got %s" % type(result["body"]).__name__)
    expect(result["body"] == expected, "body is not exactly the bytes that the server sent")
    expect(result["content_type"] == "text/html",
           "content_type should be 'text/html' (no charset, lowercase), got %r" % (result["content_type"],))
    expect(result["url"] == url, "url should be the URL you were asked to fetch")
    expect(result["final_url"] == url, "final_url should be %r, got %r" % (url, result["final_url"]))
    expect(not result["from_cache"], "from_cache should be False on the first fetch")


@_case(1, 2, "every request sends the User-Agent")
def t1_user_agent(ctx: Context) -> None:
    agent = "IRHomeworkBot/1.0 (+check-%d@innopolis.university)" % random.randint(1000, 9999)
    fetcher = ctx.fetcher("t1-agent", user_agent=agent)
    mark = ctx.sb.mark()
    fetcher.fetch(ctx.fixture("html_page"))
    fetcher.fetch(ctx.fixture("binary"))
    seen = ctx.sb.requests(since=mark)
    expect(len(seen) >= 2, "two fetches should reach the site, it received %d request(s)" % len(seen))
    wrong = [entry["user_agent"] for entry in seen if entry["user_agent"] != agent]
    if wrong:
        raise CheckFailed("%d request(s) used the User-Agent %r instead of %r" % (len(wrong), wrong[0], agent))
    expect(getattr(fetcher, "user_agent", None) == agent,
           "keep the user agent in self.user_agent, the crawler reads it from there")


@_case(1, 2, "binary files come back unchanged")
def t1_binary(ctx: Context) -> None:
    url = ctx.fixture("binary")
    expected = ctx.sb.internal_get(url).content
    result = _check_result(ctx.fetcher("t1-binary").fetch(url))
    expect(result["status"] == 200, "status should be 200, got %r" % (result["status"],))
    expect(result["body"] == expected, "the image bytes changed on the way (use response.content, not .text)")
    expect(result["content_type"] == "image/png", "content_type should be 'image/png', got %r" % (result["content_type"],))


@_case(1, 3, "disk cache: one entry per URL, reused by a new fetcher")
def t1_cache(ctx: Context) -> float:
    cls = ctx.need("PoliteFetcher")
    folder = ctx.new_dir("t1-cache")
    first = cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0)
    problems: List[str] = []
    variants = [ctx.sb.url(path) for path in ctx.theme["fixtures"]["cache_variants"]]
    pairs = [first.cache_paths(url) for url in variants]
    paths_ok = all(isinstance(pair, (tuple, list)) and len(pair) == 2 and all(isinstance(p, str) for p in pair)
                   for pair in pairs)
    if not paths_ok:
        problems.append("cache_paths must return a tuple of two strings")
    else:
        flat = [os.path.abspath(p) for pair in pairs for p in pair]
        root = os.path.abspath(folder)
        if len(set(flat)) != len(flat):
            problems.append("two different URLs (or the body and the metadata of one URL) share a cache file")
            paths_ok = False
        elif any(os.path.commonpath([root, p]) != root for p in flat):
            problems.append("cache files must be inside cache_dir")
            paths_ok = False
        elif tuple(first.cache_paths(variants[0])) != tuple(pairs[0]):
            problems.append("cache_paths gives different answers for the same URL")
            paths_ok = False

    urls = [ctx.fixture("query_a"), ctx.fixture("query_b")]
    bodies = [ctx.sb.internal_get(url).content for url in urls]
    results = [_check_result(first.fetch(url)) for url in urls]
    fetched_ok = all(result["body"] == body for result, body in zip(results, bodies))
    if not fetched_ok:
        problems.append("two URLs that differ only in the query string gave wrong bodies")
    files_ok = paths_ok and fetched_ok
    if files_ok:
        for url, body in zip(urls, bodies):
            body_path = first.cache_paths(url)[0]
            if not os.path.isfile(body_path):
                problems.append("after a fetch there is no file at cache_paths(url)[0]")
                files_ok = False
                break
            with open(body_path, "rb") as handle:
                if handle.read() != body:
                    problems.append("the body file in the cache is not the page body")
                    files_ok = False
                    break

    mark = ctx.sb.mark()
    second = cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0)
    reused = [_check_result(second.fetch(url)) for url in urls]
    contacted = len(ctx.sb.requests(since=mark))
    reuse_ok = fetched_ok and contacted == 0 and all(
        result["from_cache"] and result["body"] == body and result["status"] == 200
        and result["content_type"] == "text/html" and result["final_url"] == url
        for result, body, url in zip(reused, bodies, urls))
    if not reuse_ok:
        if contacted:
            problems.append("a new fetcher with the same cache_dir still contacted the server %d time(s)" % contacted)
        else:
            problems.append("a cache hit must return the stored status, content_type, final_url and body with from_cache True")
    points = (1 if files_ok else 0) + (2 if reuse_ok else 0)
    if points == 3:
        return 3
    raise CheckFailed(". ".join(problems), points)


@_case(1, 2, "error pages are reported and never cached")
def t1_errors(ctx: Context) -> None:
    cls = ctx.need("PoliteFetcher")
    folder = ctx.new_dir("t1-errors")
    fetcher = cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0)
    for key, code in (("missing", 404), ("broken", 500)):
        result = _check_result(fetcher.fetch(ctx.fixture(key)))
        expect(result["status"] == code, "%s should give status %d, got %r" % (ctx.fixture(key), code, result["status"]))
        expect(result["body"] is None, "body should be None when the status is %d" % code)
        expect(not result["from_cache"], "from_cache should be False here")
    mark = ctx.sb.mark()
    again = _check_result(cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0).fetch(ctx.fixture("missing")))
    expect(again["status"] == 404 and not again["from_cache"] and len(ctx.sb.requests(since=mark)) == 1,
           "a 404 response was served from the cache, but only status 200 may be cached")


@_case(1, 1, "redirects are followed and cached under the requested URL")
def t1_redirect(ctx: Context) -> None:
    cls = ctx.need("PoliteFetcher")
    folder = ctx.new_dir("t1-redirect")
    source, target = ctx.fixture("redirect"), ctx.fixture("redirect_target")
    expected = ctx.sb.internal_get(target).content
    result = _check_result(cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0).fetch(source))
    expect(result["status"] == 200 and result["body"] == expected, "the redirect was not followed to the new page")
    expect(result["url"] == source, "url must stay the URL you were asked to fetch")
    expect(result["final_url"] == target, "final_url should be %r, got %r" % (target, result["final_url"]))
    mark = ctx.sb.mark()
    cached = _check_result(cls(cache_dir=folder, user_agent=ctx.ua, delay=0.0, timeout=5.0).fetch(source))
    expect(cached["from_cache"] and cached["body"] == expected and cached["final_url"] == target
           and not ctx.sb.requests(since=mark),
           "fetching the old address again should come from the cache and keep final_url")


@_case(1, 2, "timeouts and connection errors give status None")
def t1_failures(ctx: Context) -> float:
    fetcher = ctx.fetcher("t1-failures", timeout=0.5)
    cases = [
        ("a page that answers after 3 seconds (timeout=0.5)", ctx.sb.url("/_test/slow?seconds=3"), 2.5),
        ("a port where nothing listens", ctx.sb.closed + "/", 4.0),
        ("a redirect loop", ctx.fixture("loop"), 10.0),
    ]
    passed = 0
    problems = []
    for label, url, max_time in cases:
        started = time.perf_counter()
        try:
            result = fetcher.fetch(url)
        except CheckTimeout:
            raise
        except Exception as exc:
            problems.append("%s: fetch raised %s instead of returning status None" % (label, type(exc).__name__))
            continue
        elapsed = time.perf_counter() - started
        if not isinstance(result, dict) or result.get("status") is not None or result.get("body") is not None:
            status = result.get("status") if isinstance(result, dict) else result
            problems.append("%s: expected status None and body None, got status %r" % (label, status))
        elif elapsed > max_time:
            problems.append("%s: took %.1f s, pass timeout to requests" % (label, elapsed))
        else:
            passed += 1
    if passed == len(cases):
        return 2
    raise CheckFailed(". ".join(problems), 1 if passed == 2 else 0)


@_case(1, 2, "delay between requests to the same host")
def t1_delay(ctx: Context) -> float:
    urls = [ctx.sb.url(path) for path in ctx.theme["fixtures"]["delay_urls"]]

    def global_delay() -> None:
        fetcher = ctx.fetcher("t1-delay", delay=0.4)
        mark = ctx.sb.mark()
        for url in urls:
            fetcher.fetch(url)
        times = [entry["time"] for entry in ctx.sb.requests(since=mark)]
        expect(len(times) == len(urls), "expected %d requests, the site received %d" % (len(urls), len(times)))
        gap = min(b - a for a, b in zip(times, times[1:]))
        expect(gap >= 0.36, "with delay=0.4 two requests came only %.2f s apart" % gap)
        started = time.perf_counter()
        hit = _check_result(fetcher.fetch(urls[-1]))
        expect(hit["from_cache"], "fetching a URL a second time did not use the cache")
        expect(time.perf_counter() - started < 0.2, "a cache hit waited for the delay, cache hits must return at once")

    def host_delay() -> None:
        fetcher = ctx.fetcher("t1-host-delay", delay=0.0)
        fetcher.set_host_delay(ctx.sb.netloc("main"), 0.7)
        mark = ctx.sb.mark()
        fetcher.fetch(urls[0])
        fetcher.fetch(urls[1])
        started = time.perf_counter()
        fetcher.fetch(ctx.sb.partner_url(ctx.theme["fixtures"]["partner_page"]))
        other = time.perf_counter() - started
        times = [entry["time"] for entry in ctx.sb.requests(since=mark, host="main")]
        expect(len(times) == 2, "expected 2 requests to the museum site, got %d" % len(times))
        expect(times[1] - times[0] >= 0.63, "set_host_delay(host, 0.7) was ignored, the gap was %.2f s" % (times[1] - times[0]))
        expect(other < 0.35, "a request to a different host waited, delays are per host")

    results = [_attempt(ctx, global_delay), _attempt(ctx, host_delay)]
    points = sum(1 for ok, _ in results if ok)
    if points == 2:
        return 2
    raise CheckFailed(". ".join(message for ok, message in results if not ok), points)


@_case(1, 4, "download streams big files safely", limit=90)
def t1_download(ctx: Context) -> float:
    fetcher = ctx.fetcher("t1-download")

    def small() -> None:
        folder = ctx.new_dir("dl-small")
        path = os.path.join(folder, "small.bin")
        expected = ctx.sb.download_digest("/downloads/small.bin")
        digest = fetcher.download(ctx.sb.url("/downloads/small.bin"), path)
        expect(digest == expected, "download returned %s, expected the SHA-256 hex digest %s..." % (_short(digest, 30), expected[:16]))
        expect(os.path.isfile(path) and _file_sha256(path) == expected, "the file on disk is not the downloaded file")
        leftovers = sorted(set(os.listdir(folder)) - {"small.bin"})
        expect(not leftovers, "temporary files were left behind: %s" % leftovers)

    def memory() -> None:
        import tracemalloc
        folder = ctx.new_dir("dl-big")
        path = os.path.join(folder, "big.bin")
        expected = ctx.sb.download_digest("/downloads/big.bin")
        already = tracemalloc.is_tracing()
        if already:
            tracemalloc.reset_peak()
        else:
            tracemalloc.start()
        try:
            digest = fetcher.download(ctx.sb.url("/downloads/big.bin"), path)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            if not already:
                tracemalloc.stop()
        expect(digest == expected, "the 32 MiB download failed or returned a wrong digest")
        expect(peak < MEMORY_LIMIT, "memory use peaked at %.1f MiB for a 32 MiB file, stay under %d MiB by streaming in chunks"
               % (peak / MIB, MEMORY_LIMIT // MIB))

    def failure(name: str, label: str) -> Callable[[], None]:
        def run() -> None:
            folder = ctx.new_dir("dl-" + name)
            result = fetcher.download(ctx.sb.url("/downloads/%s.bin" % name), os.path.join(folder, name + ".bin"))
            expect(result is None, "%s returned %s instead of None" % (label, _short(result, 30)))
            expect(not os.listdir(folder), "%s left files behind: %s" % (label, sorted(os.listdir(folder))))
        return run

    parts = [small, memory, failure("broken", "a download cut off halfway"),
             failure("tampered", "a download with a wrong checksum")]
    results = [_attempt(ctx, part) for part in parts]
    points = sum(1 for ok, _ in results if ok)
    if points == 4:
        return 4
    raise CheckFailed(". ".join(message for ok, message in results if not ok), points)


# -- Task 2 ------------------------------------------------------------------

@_case(2, 6, "normalize_url (6 groups of cases)")
def t2_normalize(ctx: Context) -> float:
    func = ctx.need("normalize_url")
    groups: Dict[str, List[str]] = {}
    for group, url, base, expected in ctx.tables["normalize"]:
        groups.setdefault(group, [])
        try:
            got: Any = func(url, base)
        except CheckTimeout:
            raise
        except Exception as exc:
            got = "%s: %s" % (type(exc).__name__, exc)
        if got != expected:
            call = "normalize_url(%r%s)" % (url, ", %r" % base if base is not None else "")
            groups[group].append("%s returned %s, expected %r" % (call, _short(got, 80), expected))
    failed = {group: problems for group, problems in groups.items() if problems}
    if not failed:
        return 6
    message = ". ".join("%s: %s" % (group, problems[0]) for group, problems in failed.items())
    raise CheckFailed(message, 6 * (len(groups) - len(failed)) / len(groups))


def _parse_runs(ctx: Context) -> Dict[str, Tuple[Any, Optional[str]]]:
    if "parse" not in ctx.cache:
        func = ctx.need("parse_page")
        runs = {}
        for path, page_url in ctx.theme["parse_pages"].items():
            address = ctx.sb.url(path)
            html = ctx.sb.internal_get(address).content
            try:
                runs[path] = (func(html, ctx.sb.url(page_url) if page_url else address), None)
            except CheckTimeout:
                raise
            except Exception as exc:
                runs[path] = (None, _describe_exception(exc, ctx))
        ctx.cache["parse"] = runs
    return ctx.cache["parse"]


def _parse_field(ctx: Context, field: str, compare: Callable[[Any, Any, str], Optional[str]]) -> Tuple[int, int, List[str]]:
    runs = _parse_runs(ctx)
    good = 0
    problems = []
    for path, (result, error) in runs.items():
        if error:
            problems.append("parse_page failed on %s: %s" % (path, error))
        elif not isinstance(result, dict) or field not in result:
            problems.append("parse_page must return a dict with the key %r" % field)
        else:
            message = compare(result[field], ctx.exp["parse"][path][field], path)
            if message:
                problems.append(message)
            else:
                good += 1
    return good, len(runs), problems


def _list_difference(got: List[Any], expected: List[Any], what: str) -> Optional[str]:
    if got == expected:
        return None
    for index, (a, b) in enumerate(zip(got, expected)):
        if a != b:
            return "%s: item %d is %s, expected %s" % (what, index, _short(a, 90), _short(b, 90))
    if len(got) > len(expected):
        return "%s: %d items, expected %d. The first extra one is %s" % (what, len(got), len(expected), _short(got[len(expected)], 90))
    return "%s: %d items, expected %d. The first missing one is %s" % (what, len(got), len(expected), _short(expected[len(got)], 90))


def _links_valid(got: Any) -> bool:
    return isinstance(got, list) and all(isinstance(item, dict) and {"text", "url", "nofollow"} <= set(item) for item in got)


@_case(2, 2, "title, canonical and meta_robots")
def t2_meta(ctx: Context) -> float:
    def same(label: str) -> Callable[[Any, Any, str], Optional[str]]:
        return lambda got, exp, path: None if got == exp else "%s on %s is %s, expected %s" % (label, path, _short(got, 80), _short(exp, 80))

    def robots(got: Any, exp: Any, path: str) -> Optional[str]:
        if isinstance(got, str) or not isinstance(got, (set, frozenset, list, tuple)):
            return "meta_robots must be a set of strings"
        return None if set(got) == set(exp) else "meta_robots on %s is %s, expected %s" % (path, sorted(got), sorted(exp))

    titles = _parse_field(ctx, "title", same("title"))
    others = [_parse_field(ctx, "canonical", same("canonical")), _parse_field(ctx, "meta_robots", robots)]
    problems = titles[2] + [p for item in others for p in item[2]]
    if not problems:
        return 2
    raise CheckFailed(problems[0], 1 if not titles[2] else 0)


@_case(2, 2, "links: URLs in document order")
def t2_link_urls(ctx: Context) -> float:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not _links_valid(got):
            return "links must be a list of dicts with the keys text, url and nofollow"
        return _list_difference([item["url"] for item in got], [item["url"] for item in exp], "link URLs on " + path)
    good, total, problems = _parse_field(ctx, "links", compare)
    if not problems:
        return 2
    raise CheckFailed(problems[0], 1 if good >= 0.7 * total else 0)


@_case(2, 1, "links: anchor text")
def t2_link_text(ctx: Context) -> None:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not _links_valid(got):
            return "links must be a list of dicts with the keys text, url and nofollow"
        return _list_difference([item["text"] for item in got], [item["text"] for item in exp], "link texts on " + path)
    problems = _parse_field(ctx, "links", compare)[2]
    expect(not problems, problems[0] if problems else "")


@_case(2, 1, "links: nofollow flags")
def t2_link_nofollow(ctx: Context) -> None:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not _links_valid(got):
            return "links must be a list of dicts with the keys text, url and nofollow"
        return _list_difference([bool(item["nofollow"]) for item in got], [item["nofollow"] for item in exp],
                                "nofollow flags on " + path)
    problems = _parse_field(ctx, "links", compare)[2]
    expect(not problems, problems[0] if problems else "")


@_case(2, 2, "images")
def t2_images(ctx: Context) -> float:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not isinstance(got, list):
            return "images must be a list of URL strings"
        return _list_difference(got, exp, "images on " + path)
    good, total, problems = _parse_field(ctx, "images", compare)
    if not problems:
        return 2
    raise CheckFailed(problems[0], 1 if good >= 0.7 * total else 0)


@_case(2, 3, "paragraphs")
def t2_paragraphs(ctx: Context) -> float:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not isinstance(got, list):
            return "paragraphs must be a list of strings"
        return _list_difference(got, exp, "paragraphs on " + path)
    good, total, problems = _parse_field(ctx, "paragraphs", compare)
    if not problems:
        return 3
    raise CheckFailed(problems[0], 2 if good >= 0.7 * total else (1 if good >= 0.4 * total else 0))


@_case(2, 2, "visible text")
def t2_text(ctx: Context) -> float:
    def compare(got: Any, exp: Any, path: str) -> Optional[str]:
        if not isinstance(got, str):
            return "text must be a string"
        got_words, exp_words = Counter(_tokens(got)), Counter(_tokens(exp))
        overlap = sum((got_words & exp_words).values())
        precision = overlap / max(1, sum(got_words.values()))
        recall = overlap / max(1, sum(exp_words.values()))
        if precision < 0.97 or recall < 0.97:
            missing = list((exp_words - got_words).elements())[:4]
            extra = list((got_words - exp_words).elements())[:4]
            return "text on %s does not match the visible body text (missing words %s, unexpected words %s)" % (path, missing, extra)
        if got != " ".join(got.split()):
            return "text on %s must have all whitespace collapsed to single spaces" % path
        return None
    good, total, problems = _parse_field(ctx, "text", compare)
    if not problems:
        return 2
    raise CheckFailed(problems[0], 1 if good >= 0.7 * total else 0)


@_case(2, 1, "nothing from scripts, styles, templates or hidden elements")
def t2_hidden(ctx: Context) -> None:
    markers = set(ctx.theme["markers"])
    hidden_urls = {ctx.sb.url(path) for path in ctx.theme.get("hidden_targets", [])}
    for path, (result, error) in _parse_runs(ctx).items():
        expect(error is None and isinstance(result, dict), "parse_page failed on %s" % path)
        words = set(_tokens(str(result.get("text", "")))) | set(_tokens(" ".join(map(str, result.get("paragraphs") or []))))
        leaked = sorted(words & markers)
        expect(not leaked, "text from a removed element (%s) appears on %s" % (", ".join(leaked), path))
        urls = {item.get("url") for item in (result.get("links") or []) if isinstance(item, dict)}
        urls |= set(result.get("images") or [])
        found = sorted(urls & hidden_urls)
        expect(not found, "a link or image inside a removed element was returned on %s: %s" % (path, found[0] if found else ""))


# -- Task 3 ------------------------------------------------------------------

def _call(func: Callable, *args: Any) -> Any:
    try:
        return func(*args)
    except CheckTimeout:
        raise
    except Exception as exc:
        return "%s: %s" % (type(exc).__name__, exc)


@_case(3, 4, "split_sentences (4 groups of cases)")
def t3_split(ctx: Context) -> float:
    func = ctx.need("split_sentences")
    groups: Dict[str, List[str]] = {}
    for group, text, expected in ctx.tables["split"]:
        groups.setdefault(group, [])
        got = _call(func, text)
        if got != expected:
            groups[group].append("split_sentences(%s) returned %s, expected %s" % (_short(text, 70), _short(got, 90), _short(expected, 90)))
    failed = {group: problems for group, problems in groups.items() if problems}
    if not failed:
        return 4
    raise CheckFailed(". ".join("%s: %s" % (g, p[0]) for g, p in failed.items()), 4 * (len(groups) - len(failed)) / len(groups))


@_case(3, 2, "tokenize")
def t3_tokenize(ctx: Context) -> float:
    func = ctx.need("tokenize")
    good, first = 0, None
    for text, expected in ctx.tables["tokenize"]:
        got = _call(func, text)
        if got == expected:
            good += 1
        elif first is None:
            first = "tokenize(%r) returned %s, expected %s" % (text, _short(got, 80), expected)
    return _scaled(good, len(ctx.tables["tokenize"]), 2, first)


@_case(3, 2, "top_terms")
def t3_top_terms(ctx: Context) -> float:
    func = ctx.need("top_terms")
    cases = ctx.exp["tables"]["top_terms"]
    good, first = 0, None
    for texts, n, expected in cases:
        got = _call(func, list(texts), n)
        normalized = [tuple(item) for item in got] if isinstance(got, list) and all(isinstance(i, (list, tuple)) for i in got) else got
        if normalized == [tuple(item) for item in expected]:
            good += 1
        elif first is None:
            first = "top_terms(%s, %d) returned %s, expected %s" % (_short(texts, 60), n, _short(got, 80), [tuple(i) for i in expected])
    return _scaled(good, len(cases), 2, first)


@_case(3, 4, "rank_sentences (order 2, ties 1, empty cases 1)")
def t3_rank(ctx: Context) -> float:
    func = ctx.need("rank_sentences")
    weights = {"order": 2, "ties": 1, "empty": 1}
    failed: Dict[str, str] = {}
    for group, question, sentences, expected in ctx.exp["tables"]["rank"]:
        got = _call(func, question, list(sentences))
        if got != expected and group not in failed:
            failed[group] = "rank_sentences(%r, <%d sentences>) returned %s, expected %s" % (question, len(sentences), _short(got, 60), expected)
    if not failed:
        return 4
    raise CheckFailed(". ".join(failed.values()), sum(w for g, w in weights.items() if g not in failed))


@_case(3, 1, "precision_at_k and reciprocal_rank")
def t3_metrics(ctx: Context) -> None:
    for name, ranked, relevant, k, expected in ctx.tables["metrics"]:
        got = _call(ctx.need(name), list(ranked), set(relevant), k)
        ok = isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - expected) < 1e-6
        expect(ok, "%s(%s, %s, %d) returned %s, expected %.4f" % (name, ranked, set(relevant) or "set()", k, _short(got, 60), expected))


@_case(3, 2, "best_answer on the museum pages")
def t3_best_answer(ctx: Context) -> float:
    func = ctx.need("best_answer")
    pages = ctx.exp["qa_pages"]
    good, first = 0, None
    for question, expected in ctx.exp["qa"]:
        got = _call(func, question, copy.deepcopy(pages))
        normalized = list(got) if isinstance(got, (list, tuple)) else got
        if normalized == expected:
            good += 1
        elif first is None:
            first = "best_answer(%r) returned %s, expected %s" % (question, _short(got, 100), _short(tuple(expected) if expected else None, 100))
    return _scaled(good, len(ctx.exp["qa"]), 2, first)


# -- Task 4 ------------------------------------------------------------------

def _crawl(ctx: Context, name: str, take: Optional[int] = None) -> Dict[str, Any]:
    key = ("crawl", name, take)
    if key in ctx.cache:
        return ctx.cache[key]
    spec = ctx.theme["crawl"][name]
    crawler_class = ctx.need("Crawler")
    fetcher_class = ctx.reference.PoliteFetcher if ctx.reference is not None else ctx.need("PoliteFetcher")
    fetcher = fetcher_class(cache_dir=ctx.new_dir("t4-" + name), user_agent=ctx.ua, delay=0.0, timeout=5.0)
    kwargs: Dict[str, Any] = {"max_pages": spec["max_pages"], "max_depth": spec["max_depth"]}
    if "hosts" in spec:
        kwargs["allowed_hosts"] = {ctx.sb.netloc(host) for host in spec["hosts"]}
    run: Dict[str, Any] = {"records": [], "error": None, "crawler": None}
    mark = ctx.sb.mark()
    try:
        crawler = crawler_class(ctx.sb.host_url(spec["start"][0], spec["start"][1]), fetcher, **kwargs)
        run["crawler"] = crawler
        records = crawler.crawl()
        if records is None:
            raise CheckFailed("crawl() returned None. It must be a generator that yields one dict per page")
        for record in records:
            run["records"].append(record)
            if len(run["records"]) >= (take or 200):
                break
    except (CheckFailed, CheckTimeout):
        raise
    except Exception as exc:
        run["error"] = _describe_exception(exc, ctx)
    if take:
        time.sleep(0.2)
    run["requests"] = ctx.sb.requests(since=mark)
    ctx.cache[key] = run
    return run


def _pairs(run: Dict[str, Any]) -> List[Tuple[Any, Any]]:
    pairs = []
    for record in run["records"]:
        if not isinstance(record, dict):
            raise CheckFailed("crawl() must yield dicts, it yielded %s" % type(record).__name__)
        pairs.append((record.get("url"), record.get("depth")))
    return pairs


def _expected_pairs(ctx: Context, name: str) -> List[Tuple[str, int]]:
    return [(record["url"], record["depth"]) for record in ctx.exp["crawl"][name]["records"]]


def _page_requests(run: Dict[str, Any]) -> List[Tuple[str, str]]:
    return [(entry["host"], entry["path"]) for entry in run["requests"]
            if entry["method"] == "GET" and entry["path"] != "/robots.txt"]


@_case(4, 6, "yields exactly the right pages", limit=90)
def t4_pages(ctx: Context) -> float:
    run = _crawl(ctx, "A")
    got = [url for url, _ in _pairs(run)]
    expected = [url for url, _ in _expected_pairs(ctx, "A")]
    note = " The crawl stopped with an error: %s" % run["error"] if run["error"] else ""
    if sorted(got) == sorted(expected):
        if note:
            raise CheckFailed("all pages were yielded, but" + note[len(" The crawl"):], 4)
        return 6
    got_set, expected_set = set(got), set(expected)
    parts = []
    missing = [url for url in expected if url not in got_set]
    extra = [url for url in got if url not in expected_set]
    if missing:
        parts.append("%d page(s) are missing, for example %s" % (len(missing), missing[0]))
    if extra:
        parts.append("%d page(s) should not be yielded, for example %s" % (len(extra), extra[0]))
    if len(got) != len(got_set):
        parts.append("%d page(s) were yielded more than once" % (len(got) - len(got_set)))
    overlap = len(got_set & expected_set) / max(1, len(got_set | expected_set))
    points = 3 if overlap >= 0.8 and len(got) == len(got_set) else 0
    raise CheckFailed(". ".join(parts) + "." + note, points)


@_case(4, 4, "breadth-first order and depths", limit=90)
def t4_order(ctx: Context) -> float:
    got = _pairs(_crawl(ctx, "A"))
    expected = _expected_pairs(ctx, "A")
    if got == expected:
        return 4
    if [u for u, _ in got] == [u for u, _ in expected]:
        url, depth, want = next((a[0], a[1], b[1]) for a, b in zip(got, expected) if a != b)
        raise CheckFailed("the order is right but %s has depth %r, expected %r" % (url, depth, want), 2)
    message = _list_difference([u for u, _ in got], [u for u, _ in expected], "yielded pages in breadth-first order")
    raise CheckFailed(message or "the order is wrong")


@_case(4, 3, "records have url, depth, title and links", limit=90)
def t4_fields(ctx: Context) -> float:
    run = _crawl(ctx, "A")
    expected = {record["url"]: record for record in ctx.exp["crawl"]["A"]["records"]}
    title_problem = links_problem = None
    compared = 0
    for record in run["records"]:
        if not isinstance(record, dict) or not {"url", "depth", "title", "links"} <= set(record):
            raise CheckFailed("each record must be a dict with the keys url, depth, title and links")
        want = expected.get(record["url"])
        if want is None:
            continue
        compared += 1
        if title_problem is None and record["title"] != want["title"]:
            title_problem = "the title of %s is %s, expected %s" % (record["url"], _short(record["title"], 60), _short(want["title"], 60))
        links = record["links"]
        if links_problem is None and (not isinstance(links, list) or links != want["links"]):
            links_problem = ("links of %s are wrong. They must be the list of link URLs (strings) that "
                             "parse_page returns, in document order" % record["url"])
    expect(compared >= max(1, len(expected) // 2), "too few of the right pages were yielded to check the records")
    if not title_problem and not links_problem:
        return 3
    raise CheckFailed(". ".join(p for p in (title_problem, links_problem) if p), 0 if title_problem else 1)


@_case(4, 4, "robots.txt is respected", limit=90)
def t4_robots(ctx: Context) -> float:
    runs = {"A": _crawl(ctx, "A"), "C": _crawl(ctx, "C")}
    expect(_page_requests(runs["A"]), "the crawler requested no pages at all")
    parsers = {}
    for host, text in (("main", ctx.theme["robots"]), ("partner", ctx.theme["partner"]["robots"])):
        parser = RobotFileParser()
        parser.parse(text.splitlines())
        parsers[host] = parser
    points = 0
    problems = []
    forbidden = [ctx.sb.host_url(host, path) for run in runs.values() for host, path in _page_requests(run)
                 if not parsers[host].can_fetch(ctx.ua, ctx.sb.host_url(host, path))]
    if forbidden:
        problems.append("robots.txt forbids %s, but the crawler requested it" % forbidden[0])
    else:
        points += 2
    counts_ok = True
    for name, run in runs.items():
        counts = dict(Counter(entry["host"] for entry in run["requests"] if entry["path"] == "/robots.txt"))
        if counts != ctx.exp["crawl"][name]["robots"]:
            counts_ok = False
            problems.append("robots.txt must be downloaded exactly once per host (crawl %s downloaded it %s times)" % (name, counts or 0))
            break
    if counts_ok:
        points += 1
    blocked = getattr(runs["A"]["crawler"], "blocked", None)
    expected_blocked = set(ctx.exp["crawl"]["A"]["blocked"])
    if isinstance(blocked, (list, tuple, set)) and set(blocked) == expected_blocked:
        points += 1
    else:
        problems.append("self.blocked should contain %s, got %s" % (sorted(expected_blocked), _short(blocked, 150)))
    if points == 4:
        return 4
    raise CheckFailed(". ".join(problems), points)


@_case(4, 3, "requests only what it needs, each page once", limit=90)
def t4_requests(ctx: Context) -> float:
    got = _page_requests(_crawl(ctx, "A"))
    expect(got, "the crawler requested no pages at all")
    expected = [tuple(item) for item in ctx.exp["crawl"]["A"]["requests"]]
    points = 0
    problems = []
    missing = sorted(set(expected) - set(got))
    extra = sorted(set(got) - set(expected))
    if not missing and not extra:
        points += 2
    if extra:
        problems.append("the crawler requested %s, which it should skip" % ctx.sb.host_url(*extra[0]))
    if missing:
        problems.append("the crawler never requested %s" % ctx.sb.host_url(*missing[0]))
    expected_counts, got_counts = Counter(expected), Counter(got)
    repeated = [key for key, count in got_counts.items() if count > max(1, expected_counts.get(key, 0))]
    if repeated:
        problems.append("%s was requested %d times" % (ctx.sb.host_url(*repeated[0]), got_counts[repeated[0]]))
    else:
        points += 1
    if points == 3:
        return 3
    raise CheckFailed(". ".join(problems), points)


@_case(4, 2, "errors and redirects", limit=90)
def t4_errors(ctx: Context) -> float:
    run = _crawl(ctx, "A")
    points = 0
    problems = []
    expected = {(url, status) for url, status in ctx.exp["crawl"]["A"]["errors"]}
    try:
        got = {(url, status) for url, status in getattr(run["crawler"], "errors")}
    except Exception:
        got = None
        problems.append("self.errors must be a list of (url, status) tuples")
    if got is not None:
        if got == expected:
            points += 1
        else:
            order = lambda pair: (str(pair[0]), str(pair[1]))
            problems.append("self.errors should hold %s, got %s" % (sorted(expected, key=order), _short(sorted(got, key=order), 200)))
    roles = ctx.theme["crawl_roles"]
    target, source = ctx.sb.url(roles["redirect_target"]), ctx.sb.url(roles["redirect_source"])
    urls = [url for url, _ in _pairs(run)]
    if urls.count(target) == 1 and source not in urls:
        points += 1
    else:
        problems.append("after the redirect from %s the record must use the final URL, and a final URL that was "
                        "already seen must be skipped (it was yielded %d times)" % (source, urls.count(target)))
    if points == 2:
        return 2
    raise CheckFailed(". ".join(problems), points)


@_case(4, 2, "meta robots noindex and nofollow", limit=90)
def t4_meta(ctx: Context) -> float:
    run = _crawl(ctx, "A")
    roles = ctx.theme["crawl_roles"]
    urls = {url for url, _ in _pairs(run)}
    requested = {path for host, path in _page_requests(run) if host == "main"}
    points = 0
    problems = []
    if ctx.sb.url(roles["noindex_page"]) not in urls and ctx.sb.url(roles["noindex_child"]) in urls:
        points += 1
    else:
        problems.append("a noindex page must not be yielded, but its links must still be followed (%s)" % roles["noindex_page"])
    if ctx.sb.url(roles["nofollow_page"]) in urls and roles["nofollow_child"] not in requested:
        points += 1
    else:
        problems.append("a page with meta nofollow must be yielded, but none of its links may be followed (%s)" % roles["nofollow_page"])
    if points == 2:
        return 2
    raise CheckFailed(". ".join(problems), points)


@_case(4, 2, "max_pages and max_depth", limit=90)
def t4_limits(ctx: Context) -> float:
    points = 0
    problems = []
    run_b = _crawl(ctx, "B")
    spec_b = ctx.theme["crawl"]["B"]
    if _pairs(run_b) == _expected_pairs(ctx, "B") and len(_page_requests(run_b)) == len(ctx.exp["crawl"]["B"]["requests"]):
        points += 1
    else:
        problems.append("with max_pages=%d the crawler should stop after %d fetch attempts (it yielded %d pages and made %d page requests, "
                        "expected %d and %d)" % (spec_b["max_pages"], spec_b["max_pages"], len(run_b["records"]), len(_page_requests(run_b)),
                                                 len(ctx.exp["crawl"]["B"]["records"]), len(ctx.exp["crawl"]["B"]["requests"])))
    run_d = _crawl(ctx, "D")
    if _pairs(run_d) == _expected_pairs(ctx, "D"):
        points += 1
    else:
        message = _list_difference(_pairs(run_d), _expected_pairs(ctx, "D"), "with max_depth=1, the (url, depth) records")
        problems.append(message or "max_depth is not respected")
    if points == 2:
        return 2
    raise CheckFailed(". ".join(problems), points)


@_case(4, 2, "crawl() is lazy", limit=90)
def t4_lazy(ctx: Context) -> None:
    take = ctx.theme.get("lazy_take", 2)
    run = _crawl(ctx, "A", take=take)
    expect(len(run["records"]) == take, "crawl() yielded fewer than %d records" % take)
    made = len(_page_requests(run))
    allowed = ctx.exp["lazy_requests"]
    expect(made <= allowed + 1, "after taking %d records the site had already received %d page requests (about %d expected). "
                                "crawl() must fetch the next page only when the next record is requested" % (take, made, allowed))


@_case(4, 2, "two hosts and Crawl-delay", limit=90)
def t4_hosts(ctx: Context) -> float:
    run = _crawl(ctx, "C")
    points = 0
    problems = []
    if _pairs(run) == _expected_pairs(ctx, "C"):
        points += 1
    else:
        problems.append(_list_difference(_pairs(run), _expected_pairs(ctx, "C"), "records of the two-host crawl") or "wrong records")
    times = [entry["time"] for entry in run["requests"] if entry["host"] == "partner"]
    gaps = [b - a for a, b in zip(times, times[1:])]
    if len(times) >= 3 and min(gaps) >= 0.9:
        points += 1
    else:
        smallest = "%.2f s" % min(gaps) if gaps else "no gap"
        problems.append("the partner site asks for Crawl-delay: 1, but its requests came %s apart" % smallest)
    if points == 2:
        return 2
    raise CheckFailed(". ".join(problems), points)


# -- Task 5 ------------------------------------------------------------------

def _same_product(got: Any, want: Dict[str, Any]) -> bool:
    if not isinstance(got, dict):
        return False
    if type(got.get("id")) is not int or got.get("id") != want["id"]:
        return False
    if got.get("name") != want["name"] or got.get("tags") != want["tags"] or bool(got.get("in_stock")) != want["in_stock"]:
        return False
    if not isinstance(got.get("in_stock"), bool):
        return False
    for key in ("price", "rating"):
        value, target = got.get(key), want[key]
        if target is None:
            if value is not None:
                return False
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or abs(value - target) > 0.005:
            return False
    return True


@_case(5, 3, "parse_price")
def t5_price(ctx: Context) -> float:
    func = ctx.need("parse_price")
    good, first = 0, None
    for value, expected in ctx.tables["price"]:
        got = _call(func, value)
        if expected is None:
            ok = got is None
        else:
            ok = isinstance(got, (int, float)) and not isinstance(got, bool) and abs(got - expected) < 0.005
        if ok:
            good += 1
        elif first is None:
            first = "parse_price(%r) returned %s, expected %r" % (value, _short(got, 60), expected)
    return _scaled(good, len(ctx.tables["price"]), 3, first)


@_case(5, 3, "normalize_product")
def t5_product(ctx: Context) -> float:
    func = ctx.need("normalize_product")
    good, first = 0, None
    for raw, expected in ctx.tables["product"]:
        got = _call(func, copy.deepcopy(raw))
        if _same_product(got, expected):
            good += 1
        elif first is None:
            first = "normalize_product(%s) returned %s, expected %s" % (_short(raw, 120), _short(got, 120), expected)
    return _scaled(good, len(ctx.tables["product"]), 3, first)


@_case(5, 5, "scrape_shop collects the whole catalog", limit=60)
def t5_scrape(ctx: Context) -> float:
    func = ctx.need("scrape_shop")
    mark = ctx.sb.mark()
    error = None
    products: Any = None
    try:
        products = func(ctx.fixture("shop"), ctx.ua)
    except CheckTimeout:
        raise
    except Exception as exc:
        error = _describe_exception(exc, ctx)
    api = [entry for entry in ctx.sb.requests(since=mark) if "api" in entry]
    expected = ctx.exp["shop"]
    points = 0
    problems = [error] if error else []
    if api and all(entry["api"]["token_ok"] for entry in api):
        points += 1
    elif not api:
        problems.append("the JSON API was never called (look at the shop page source for its address)")
    else:
        problems.append("some API requests had no valid token (the site answered 401)")
    cursors = sorted({entry["api"]["cursor"] for entry in api if entry["status"] == 200})
    if cursors == expected["cursors"]:
        points += 1
    else:
        problems.append("the API has %d pages, %d of them were loaded" % (len(expected["cursors"]), len(cursors)))
    throttled = [entry for entry in api if entry["api"].get("throttled")]
    if throttled and any(entry["api"]["cursor"] == throttled[0]["api"]["cursor"] and entry["status"] == 200
                         and entry["seq"] > throttled[0]["seq"] for entry in api):
        points += 1
    else:
        problems.append("after a 429 answer the request must be repeated once Retry-After seconds have passed")
    want = expected["products"]
    if isinstance(products, list) and len(products) == len(want) and all(_same_product(g, w) for g, w in zip(products, want)):
        points += 2
    elif isinstance(products, list):
        ids = [item.get("id") for item in products if isinstance(item, dict)]
        if sorted(map(str, ids)) == sorted(str(item["id"]) for item in want):
            points += 1
            problems.append("all products are there, but some are not normalized correctly or not in API order")
        else:
            problems.append("scrape_shop returned %d products, expected %d unique products in API order" % (len(products), len(want)))
    elif not error:
        problems.append("scrape_shop must return a list of product dicts")
    if points == 5:
        return 5
    raise CheckFailed(". ".join(problems), points)


@_case(5, 4, "filter_products (4 queries)")
def t5_filter(ctx: Context) -> float:
    func = ctx.need("filter_products")
    good, first = 0, None
    for query, expected in ctx.exp["tables"]["filters"]:
        try:
            got: Any = func(copy.deepcopy(ctx.exp["shop"]["products"]), **query)
        except CheckTimeout:
            raise
        except Exception as exc:
            got = "%s: %s" % (type(exc).__name__, exc)
        if got == expected:
            good += 1
        elif first is None:
            first = "filter_products(products, %s) returned %s, expected %s" % (
                ", ".join("%s=%r" % item for item in query.items()) or "no filters", _short(got, 80), expected)
    total = len(ctx.exp["tables"]["filters"])
    if good == total:
        return 4
    raise CheckFailed("%s (%d of %d queries correct)" % (first, good, total), 4 * good / total)

# ---------------------------------------------------------------------------
# Running the tests and printing the report
# ---------------------------------------------------------------------------

_MISSING = object()


def _run_check(ctx: Context, spec: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    points, message = 0.0, ""
    try:
        with _time_limit(spec["limit"]):
            earned = spec["func"](ctx)
        points = spec["points"] if earned is None else max(0.0, min(spec["points"], float(earned)))
    except CheckFailed as exc:
        points, message = max(0.0, min(spec["points"], float(exc.points))), str(exc)
    except CheckTimeout:
        message = "this test needed more than %g seconds and was stopped" % spec["limit"]
    except Exception as exc:
        message = _describe_exception(exc, ctx)
    return {"name": spec["name"], "title": spec["title"], "points": round(points, 2),
            "max": spec["points"], "message": message, "seconds": round(time.perf_counter() - started, 1)}


def run_task(task: int, ns: Dict[str, Any], sb: Sandbox, expected: Dict[str, Any], workdir: str,
             student_file: Optional[str] = None, reference: Any = None,
             emit: Optional[Callable[[Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    os.makedirs(workdir, exist_ok=True)
    ctx = Context(ns, sb, expected, workdir, student_file=student_file, reference=reference)
    replaced: Dict[str, Any] = {}
    if task == 4 and reference is not None:
        replaced = {"parse_page": reference.parse_page, "normalize_url": reference.normalize_url}
    saved = {name: ns.get(name, _MISSING) for name in replaced}
    ns.update(replaced)
    checks = []
    try:
        for spec in _CHECKS[task]:
            outcome = _run_check(ctx, spec)
            checks.append(outcome)
            if emit is not None:
                emit(outcome)
    finally:
        for name, value in saved.items():
            if value is _MISSING:
                ns.pop(name, None)
            else:
                ns[name] = value
    note = ""
    if task == 4 and reference is not None:
        note = "Task 4 ran with the reference fetcher and parser, so only the Crawler class is graded here."
    return {"task": task, "title": TASK_TITLES[task], "points": round(sum(c["points"] for c in checks), 2),
            "max": TASK_POINTS[task], "checks": checks, "note": note}


def _number(value: float) -> str:
    return str(int(value)) if float(value) == int(value) else ("%.1f" % value)


def format_report(result: Dict[str, Any]) -> str:
    lines = ["Task %d  %s   %s/%s points" % (result["task"], result["title"],
                                             _number(result["points"]), _number(result["max"]))]
    for check in result["checks"]:
        if check["points"] >= check["max"]:
            status = "ok  "
        elif check["points"] > 0:
            status = "part"
        else:
            status = "FAIL"
        lines.append("  %s  %4s/%-3s %s" % (status, _number(check["points"]), _number(check["max"]), check["title"]))
        if check["message"]:
            for line in textwrap.wrap(check["message"], 92):
                lines.append("              " + line)
    if result.get("note"):
        lines.append("  (%s)" % result["note"])
    return "\n".join(lines)


def total_score(results: List[Dict[str, Any]]) -> int:
    return int(round(sum(result["points"] for result in results)))


# ---------------------------------------------------------------------------
# Expected answers, produced from the reference solution
# ---------------------------------------------------------------------------

def build_expectations(sb: Sandbox, ref: Any) -> Dict[str, Any]:
    theme, tables = sb.site.theme, sb.site.tables
    expected: Dict[str, Any] = {"parse": {}, "tables": {}, "crawl": {}}
    for path, page_url in theme["parse_pages"].items():
        address = sb.url(path)
        html = sb.internal_get(address).content
        parsed = ref.parse_page(html, sb.url(page_url) if page_url else address)
        parsed["meta_robots"] = sorted(parsed["meta_robots"])
        expected["parse"][path] = parsed

    pages = []
    for path in theme["qa"]["pages"]:
        address = sb.url(path)
        parsed = ref.parse_page(sb.internal_get(address).content, address)
        pages.append({"url": address, "paragraphs": parsed["paragraphs"]})
    expected["qa_pages"] = pages
    expected["qa"] = [[question, list(ref.best_answer(question, pages) or []) or None]
                      for question in theme["qa"]["questions"]]

    expected["tables"]["top_terms"] = [[texts, n, [list(item) for item in ref.top_terms(texts, n)]]
                                       for texts, n in tables["top_terms"]]
    expected["tables"]["rank"] = [[group, question, sentences, ref.rank_sentences(question, sentences)]
                                  for group, question, sentences in tables["rank"]]

    workdir = tempfile.mkdtemp(prefix="ir-expect-")
    try:
        for name, spec in theme["crawl"].items():
            fetcher = ref.PoliteFetcher(cache_dir=os.path.join(workdir, name), user_agent=GRADER_USER_AGENT,
                                        delay=0.0, timeout=5.0)
            kwargs: Dict[str, Any] = {"max_pages": spec["max_pages"], "max_depth": spec["max_depth"]}
            if "hosts" in spec:
                kwargs["allowed_hosts"] = {sb.netloc(host) for host in spec["hosts"]}
            crawler = ref.Crawler(sb.host_url(spec["start"][0], spec["start"][1]), fetcher, **kwargs)
            mark = sb.mark()
            records = list(crawler.crawl())
            seen = sb.requests(since=mark)
            expected["crawl"][name] = {
                "records": records,
                "errors": [list(item) for item in crawler.errors],
                "blocked": list(crawler.blocked),
                "requests": [[entry["host"], entry["path"]] for entry in seen
                             if entry["method"] == "GET" and entry["path"] != "/robots.txt"],
                "robots": dict(Counter(entry["host"] for entry in seen if entry["path"] == "/robots.txt")),
            }
        take = theme.get("lazy_take", 2)
        spec = theme["crawl"]["A"]
        fetcher = ref.PoliteFetcher(cache_dir=os.path.join(workdir, "lazy"), user_agent=GRADER_USER_AGENT,
                                    delay=0.0, timeout=5.0)
        crawler = ref.Crawler(sb.host_url(spec["start"][0], spec["start"][1]), fetcher,
                              max_pages=spec["max_pages"], max_depth=spec["max_depth"])
        mark = sb.mark()
        pump = crawler.crawl()
        for _ in range(take):
            next(pump)
        expected["lazy_requests"] = len([entry for entry in sb.requests(since=mark)
                                         if entry["method"] == "GET" and entry["path"] != "/robots.txt"])
        pump.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    mark = sb.mark()
    products = ref.scrape_shop(sb.url(theme["fixtures"]["shop"]), GRADER_USER_AGENT)
    cursors = sorted({entry["api"]["cursor"] for entry in sb.requests(since=mark)
                      if "api" in entry and entry["status"] == 200})
    expected["shop"] = {"products": products, "cursors": cursors}
    expected["tables"]["filters"] = [[query, ref.filter_products(copy.deepcopy(products), **query)]
                                     for query in tables["filters"]]
    return to_placeholders(expected, sb)


def verify_tables(tables: Dict[str, Any], ref: Any) -> List[str]:
    """Check the handwritten tables against the reference solution."""
    problems = []
    for group, url, base, expected in tables["normalize"]:
        got = ref.normalize_url(url, base)
        if got != expected:
            problems.append("normalize_url(%r, %r) -> %r, table says %r" % (url, base, got, expected))
    for group, text, expected in tables["split"]:
        got = ref.split_sentences(text)
        if got != expected:
            problems.append("split_sentences(%r) -> %r, table says %r" % (text, got, expected))
    for text, expected in tables["tokenize"]:
        if ref.tokenize(text) != expected:
            problems.append("tokenize(%r) -> %r" % (text, ref.tokenize(text)))
    for value, expected in tables["price"]:
        if ref.parse_price(value) != expected:
            problems.append("parse_price(%r) -> %r, table says %r" % (value, ref.parse_price(value), expected))
    for raw, expected in tables["product"]:
        got = ref.normalize_product(copy.deepcopy(raw))
        if got != expected:
            problems.append("normalize_product(%r) -> %r" % (raw, got))
    for name, ranked, relevant, k, expected in tables["metrics"]:
        got = getattr(ref, name)(list(ranked), set(relevant), k)
        if abs(got - expected) > 1e-9:
            problems.append("%s(%r, %r, %r) -> %r, table says %r" % (name, ranked, relevant, k, got, expected))
    return problems


# >>> GENERATED EXPECTATIONS (python ir_sandbox.py expectations --reference reference_solution.py --write)
_PRACTICE_EXPECTED = (
    "eNrtPdty28hyvzLRQ2pPhaIIirIlVaUcHa8dO7uyXZY3rsTlco2AIYElgMEOAMu0a6vOh+R8wPmCvJ9POV+S7p7BlbiQFrWh"
    "bLzYIjCXnp6+T6Pny0HEVSwOztmXgyP6N/ESH38fPA9DGUnfi9llGos0YHLOXvAkVdxnz7w4kWp1MGIHvhcuY2j/DrqKTwn2"
    "xMep8vFPN0mi86OjL5cXz1/8foQvQjmXvi9v4O2c+7H4fcSKns9kIG7Rm/t+3Nrdxbf9gzz5KMKkfRRBr/uHuXJl1DpIDC/7"
    "h7i4lmnC0nZYODboH+epwF0TDktc2MxAhol7Dn8L9p/SX3D22vsoVMwQPT24U9RyQ7hxgoAI57bwv/J5yDj76MVe8vXEcSW4"
    "sl0Cy4ZWwk48GbbvELV+9Nu/BjwIZOL2Dh94SknFAMQ2Av7w88vHFz8/e3n1ZuOVx0IQwPFS+CLpAFfvj2eLQ74QvcP+xD8D"
    "Rq9sT4S2YBewUNjYhrFfXbx+8+LJ6w2Qq7mCRWb2W3HOYyBQbie3phol4pgtvYT98OrHp39qHS7CdkfQbhw588ZR38NDL4Cl"
    "kZirdZ97voiPfLmQ4yhcYP+m965Q8tCQ0vjXaHGAY4Lk5QvFI1eP+1b4Nog/lkgg9jiAHTX8w268xIVn196iRLpj9lYwX8ol"
    "4/NEKOBrhcQCG2tNR7PJhMnrX6FlPGJzJQNGvMtiVwCh6ClgsgioCrhUw5VT2RhXsbnQGLPnCVNCRiKE5hoYDpCFC3gayo8c"
    "oWU8dFgob6BHjMuDsRcCHic8XNJ8daHB/v6/rMz4+LuVhV/C3LovjxhwoY3IS2PmzdlKpiwUAJjjKd0hpvmubFdKn5CQJrgU"
    "G+aCmZlMAZcFM8Pq9CAc0OshOG6q1GrE6rzJ5p6KExobNuZGqqXeN2zTyHCM+gjfATRpcTNmj11hL6lLiaPYHGDB1cJ+aOBx"
    "vR7g1wVg43P2JhWxw1e4rVdpCH+NmDU5BxKAB9Yp/DFmbwrEwnbavowBJQDApcT2MCoSZFkLM1KmTGtDhtqMZfqIbWAZsP2h"
    "ZrY5KbPb0zL7akJmW1Ix25SE2bY0zO6UgNnuqZf9/W9sOpk+2IQyx+yVKxMZs+tVeZcSwQMAX+se3CMvnMt/84LQHYtPHGmL"
    "NnJdqQDSZejBXgHnhKnvw6NAJPyDktcyIcn+HvTSQWZ+VkxszWP/zBbwv1CeiAeD+j4Y1M+RBzosne2ssbIU2o0BfumFAii+"
    "b7Sg1KxzPIksrqVkp4UH7bYDVJVELwi93az+27IfDS0FC/0XGJERNWwwIEtSEjVT4ioQ75FQAQ+BxQjLICqfcNA8MgTBz5cC"
    "9BfxBAjoZAU6IwRFQgoVNANZGn8GlRxwtUR5C1oFKQFJ4BGJ5BpdgCb0YCNRc8A8/wX6BhUSoECyX9MgwmFR4NY2fTvT4yUA"
    "QQthu14tM1zNzjMTAoyNG1Cw/oop1wtBY6DetzkoPl8r4Ir9ALvtxe4I7Brl6Kb5Ypkj/ISPWcaX0NZWqzjBP8mcwZa/oI66"
    "lCkQr4eD3z3m2T3Sm5kwrUaozI5loYtBc+675tTWrTbQkzRetq/tk+tde7A6q3dMXvAkGLJpRxQrH3T6XQYhDOIPc8+oo60W"
    "fIck+LraIeoPEfVdjXCn26IeKM1AEiqUOOSfkXTy0LGqe3Igt1P0vMDVMA4J+DLW2cNT7SDkzaDz8XjKQDbhUCiJtdifnYwm"
    "4FasoH+MEpQU3I8KJL/yQs5eiUSBhweOihbd4hMsjmvn9MrNZOwCZCgCB2MvmSsUeUHYnFwndoVCE70ZWI5A3UPuJs30Wvg8"
    "QWmuPdlzVmcGDWqdmrd0zUsikf1/4rbaTXvSti84en4jFqEqISoAhMBMoIROxmyTvWC33wz2lTtxn/SlsZUr6rIx3D/ozH3X"
    "ma/TOPaAIbM4U+t4RSgp2/+jcp8eJUpBpzmRKpmr20xDHQ6NB1eaJ1FpfZqIO46P/At8QHE+6NuvsI+/M4XdgGN0AbPtbPMA"
    "0TsqG/kapLgU7CR3AzDKYnAqbJF5Bo95HCGNXQluJHc5qMlckOgxs6bGxcmcG3gqQMyie4V6waqp1kshdCC0TsEjjG7qYG/C"
    "1imPOiMQtAbyYoDjblDQN1HPdgpyPea7P0hjrRhjPShjGoDNELY/eqwnzNOh3/LYVUXD5Q42IeIHEyjG6HMRvf/ToPXuUYx1"
    "k7SETQOteZRFBEglTr/amX3baqcthljhouLApcpHLA3BBmdxBAb7AoxylLt5VItrUxylEJr3iPmKZ4JDhfKGJH0WrtImvRI8"
    "8ynq+wUjAt+K7eR9VST8wctjW69tvz0MIDcvdMSnAy2KuwzOilxuMmEHEbzvIjhSMjFH0yr1RdwvL0++S3m5Zqwhx/t4QI5y"
    "oMhkODHxkTGZnD6HxmAIonWIUsgaP2ABpRro/JRsMLFYaIFjtgMkFfC7z28wjsG1TVnfqe1E5Br8d7IodqsV7a3N2uN0rwtQ"
    "Q39aghpyrwjLpvTJQVjuu7DEMzq3yIruGKrUqjv5M+HzOfJJeyiGmvTD5ig+T5Dl2hI9DXj6/ZFuvokQ9oCTroFrkOy7smnR"
    "iEr08vvTITBJCu2nNLhGn/yH/7h6+aJdwvPIA/0TSZVsrjRuoS7uQJd9iypxkwxBk2SHcRVHSgyBYLIfuwBi8UHSWzNKxsPz"
    "C9QQJmtw4c0THOx0MgFFBCoqO0LnoDI8MN3zjDqpzKkL1wfobjatYguZhXAKHhuzX8K5F4LewsQ/lXg2ap0bDvg0Fn6Vi3TS"
    "KqpHB9MNoP1SJDB3DE0sUIoqvUZFzJ6ECUzqIZRC607o7jvgaICH4QjFHtJI//jL/1yUUtwwnzFErtK+SJ6HF/E4Gf/jL3+F"
    "PVZyPmYXY/aC8hCW8uNIn+EIRXu/xpyo2pp5q6r04MdbhVmDgCIwDuBnRqDb2BRrWZD7QxVsU5Jg29IEdNgNRbCdkgPbPS3c"
    "h4OwstLpNLDYD9Q0Q041QFgVhncq7kiiOA6u+JxZQHtkTgL6k3jJVxwM6PGomIrQGopz9i8P2ensmJ2cnBxOrMOzs6rxf5eM"
    "uBNgt9jRtY9yKttqkqoBotQHoJGxgI1MU2CSwY6+D3b05Y6zgy5riQ47iiW/TrUC0CTJ+IJ7O/yY7FszCadZqgULeALoWqH2"
    "NZ8MkJHWhM1tzI0+3mddELAyzbE6wbAm4PZd/6G4JI1vDshk9CERKqC377TOyvNc9AcglGlEJi2+GGFSjQQ04B9vfrn66Z/w"
    "3XNM1JkcUw/qfsNjbWWQzjkeweAHhnFn8ODdAb2EXxb9yrLzrPfv31NbfQw7yo5fERqKLOnf+js0jCRR3AmwXmrnYz4vtfiZ"
    "Mnun9PSYALEmNHp+kKhhoR7wa6ohg3FzwHztFusfCEEJSPjnBP6nXweKh0vC4YFUYFrRx16Ud3TD40oWUTWv6tHBKDtbqb/P"
    "UVjKvdKn5yWi1OEyV/CPq/xwvJyShclY9OIF9MBPa3ROM6VEEUbeAUYsXDqtMIf9mbyhVGIvLh9NZ/ErDfVVYwDQfBSVeIHI"
    "ITLddexP8wwdhDflBrzUKc3l6ZrbAXQBj+LstFvnU5vvmIhyQQ7oJU5pibDQY73KxHxPk2dx0XIu1rK6WjKwSzsDjGus+jhf"
    "7FqWHlIi/UyA/YEg4X9MItO2F1pQ1a44usPVUsNuAM93SARRsiqoS+9PQUXZyZXe33IzL3lEA9aGKRTPu/c5MYPcTnSS2Du0"
    "h/gCJe3Sc+KD3xEkCxE6sfCfB/jPMf7zkAb+AgN++gCWoI2WlzWZTFA/hB9A3tnLDzL0V0XyTzYQMJFl0Wj406LRZtlo0FeB"
    "bxMiCLPxCUkvAgez4DN4NCi6i34yw5EKME+r8xRQU5MzfDEp5jbLIdPSVvzGJ1F5Qf8qYQOTGEux1b5zRERGKK7+q8smNIzb"
    "96QwDlvNvRYTrs2M6M7D2KxXw7QNdk//F/E9Zlnjx+kb4qFtkqoB9J6MqB6zPNt7q7z33d/z7e1ON2B3E0JY/4qs/3OwXRDa"
    "xrtVwlLjdhXe0z7vEVh6IgRVcYQG56E1aZ0py+/HbOjWRuC5nx0CffLWFqjjD+dCOOstfAmQ8zvYqRwljftkBGlsvNR93ixq"
    "bnN9GrFjJBUDNGKp89xwD1G1dhrWdrbVe0rVedjUdVzU4wZvs45bK5VCCjbubnfy/j6Kre6D8e1yyrvSwnctihqMlsYd2Sre"
    "uIcbVA2ibWUX9Bl2O2OKEgSNe9D6Beg9w3f1y8Qdo7LJgMiwOS1j87FpSLT80k7kNfja2Ol+mUiTs14jyro7a7NuhTViOg/u"
    "mEb32EfYkVlTsgMaMfayml+z/whra29OZe/C36lZPo143O7ws0OodKv3xrk704D3WWKf3IW4qBgxjfh61fKt3P2NHeWLfnCX"
    "GLX65a45XbzHcvdOTYbq4C3GwlrRhW/U2t0dNmdlbB6XsVn/Lmn/CbM97rdjg1Wbc41YqxisV9BCBPfUZD39mrjfrj0DazNE"
    "v5Af7yuem7BYazG9MxO3bPk1YhmP9sqN7nH0blOU4TmkwEqV+hiyP2Y9m+jT/N7Q9clk0tAwj2Bj5gSdgl770l5Cj3U0d8Ry"
    "Nw1OUs6A+C0VcWIWGJhEIXpX+mn2q/ow26zqU71T1WcG301jGlusNkY9gtPUM9OITe9y8V99uXbmszFEa4zaiIqKd93YoiCW"
    "xtcFiVRfG8JoeHg9tBxa/pEtq6K1+q7s4td6FScbNcbq8NRrLFK4pC0vrLYX07YXs042B9uuUwpYjajJdaTOycry3r7odufM"
    "ovy3Pw+ZHEMmx5DJMWRyDJkcQybHkMkxZHIMmRxDJseQyTFkcgyZHEMmx5DJsauYbS2GOkQ87zTi2RXweNwb8Kh42o0xj9ar"
    "AdfputFtzx+azy2rInLt7bTxranZcBTKRLT6ms0M3Dx/o8Z5SldX5XN87QKnGwIybQXkVV4MvReQIaBxvwIanaKyj/DXRWkE"
    "7mioP900kq/8pCD51lfTFhlcEytZV01DFSHz44ZR1YaIzWSI2OxjxKbdJB/i30P8e1AX+xD/HqKqQ1T1u42qdkU9rCHq8QdF"
    "Pawh6rE/mWodUZbmCMomsZeNoyxDqtbQ8rtt2RqBQ+/4N/4hyqqkdbhbtfJob4VvY4Ezusg+Duh6Vm3Smfqm196idFE83c+u"
    "7wKia/WKYuzWdDSbTLJSZyNd2kiXTIpdgRY9TYE3xvsiWa9GpStuCfTx6OI9cP3oyrzz0mVIpYNLKsWqhKkUqYExhaFKF2lg"
    "GaRQ3tAtvbx6R5KuOFb/Ig3Lnvl4fy37iDVK8bc5ocNGBR6oPhTMbQpvRVjH1UbkpTHz9IX3IUgP5njKnEjqyvq2K6VPSEix"
    "/hEVtoKZqSRs4KGIZ1jIElanBzHVpjhzU6VWI6qslZQrcNFtg7oOk6BLeIsKrY3xVEZ9MPoIOsbUoHvsCnup7zrUBe7oXl80"
    "ZHC1sB8aeFwvFvhyAdj4nL0BDYAXHMK2XqUgkldY1OgcSAAeWKfwx7h8T3Jx1wkAcCmxPV4VsIlFPdR4/k5qPG/xnW6NJqg6"
    "oDUrc7LL6WIboM8byZSUQazpsXJZDlZC446TXQRqPSzuSlu/rE3Xpczb6vqxl6rAT1J8QzHKyIQu9zF0BJiZ5VdWPMM9o6tC"
    "gSwcDQlISg4cTNUPi9pwP/GAa0mqr0XnyKxSE52+aTy/uy3LTh1vdSg+XIu79bW4W7syNRyvrxE8X59q/+HFThURX1S6JKTS"
    "Mn2OgkAjEaRBdp88gluWBQF9LBXnVyKi+I4kcO752sVR480/b12jF6wRiNiC/6fjmbl1hYC5Ed7CjdnsIVvqa1iokqGm7atk"
    "jKsH+K5BLxtS8vB6QuSENMDvjh2wPjxd+rNC/GvQg5oW+vrBpKlCovahfuPaYXnrgnh0PKcsL1BdFMqiqHe4u/rajfpNF0vE"
    "YpiJ4bKmUp4FOF/HUl0CoIAgSIE7HCmMrVRXPI9MEcs+ndSzVl0vEg2f56BvQNwFKzAy7RUoxEdll9Pnn1cfSo4mpj5QmJFO"
    "iZR0Ujsxxq7nUClIDBOEPKhECSI/jYGXpdYaWdXI6dnZeEI1VfPCj6e68KMmaapEiQ/kSp+FZQUmyxfLmlmnpVm10tBWr0k6"
    "y+acnUzqU1rlKSNAY3b3JI96Zz0uzfqUFAyYiCExuLllJJt4OjubUFnL9SqX1cXG2lKsz1zUdjZTz8po1jwRpIvylA/Oams1"
    "tYKzKXvWdlKaIC8BO1ees0DOWISisj5rHbGV5cUyBZHsqV6UPihNm8mWyCMDmF2Dy1Oe9PSse9Jrqh06MjVN+zD6sDTzY33R"
    "H1soeYO7GVdXazDZhtl8E1umrq/5tDRzU8mHOjEdN2C7wjnUq3/FZ+UV58L6zWHseqq6u9Y6piflCcGrAInZt1AsvppP+MTc"
    "e7gUK9s1Pna+wPr6jsdnG1FTfYmWtc4mi9RzRJ2UHkw2IaWe5ZWF0FtwMcHuVa4XShalnz/7ojzf2dlkI9mne/bOXBZEbyTY"
    "9dd80Sn3tpIFVlnYvABbAtQOGr7kp9lcORVJN6mj8qRKK9ireUH4zAa31oRY6WYG+9+fhv99NflU+ntV+vszGBW//x+/RhZA"
)
# <<< GENERATED EXPECTATIONS


def decode_expectations(blob: str, sb: Sandbox) -> Dict[str, Any]:
    data = json.loads(zlib.decompress(base64.b64decode(blob)).decode("utf-8"))
    return from_placeholders(data, sb)


def load_variant(path: str) -> Any:
    """A variant file defines THEME, TABLES and a generated EXPECTED blob."""
    return _load_module(os.path.abspath(path), "ir_variant")


def practice_expectations(sb: Sandbox) -> Dict[str, Any]:
    if not _PRACTICE_EXPECTED:
        raise RuntimeError("this copy of ir_sandbox.py has no expected answers stored in it, ask the teaching team for the right file")
    return decode_expectations(_PRACTICE_EXPECTED, sb)


def _write_expectations(reference_path: str, variant_path: Optional[str] = None) -> None:
    ref = _load_module(os.path.abspath(reference_path), "reference_solution")
    if variant_path:
        variant = load_variant(variant_path)
        theme, tables = variant.THEME, variant.TABLES
        target, variable = os.path.abspath(variant_path), "EXPECTED"
    else:
        theme, tables = PRACTICE_THEME, PRACTICE_TABLES
        target, variable = os.path.abspath(__file__), "_PRACTICE_EXPECTED"
    sb = Sandbox(Site(theme, tables))
    try:
        problems = verify_tables(tables, ref)
        if problems:
            print("The reference solution disagrees with the tables in %s:" % os.path.basename(target))
            for problem in problems:
                print("  " + problem)
            raise SystemExit(2)
        expected = build_expectations(sb, ref)
    finally:
        sb.stop()
    blob = base64.b64encode(zlib.compress(json.dumps(expected, ensure_ascii=False).encode("utf-8"), 9)).decode()
    lines = [blob[index:index + 96] for index in range(0, len(blob), 96)]
    literal = variable + " = (\n" + "\n".join('    "%s"' % line for line in lines) + "\n)"
    path = target
    with open(path, encoding="utf-8") as handle:
        source = handle.read()
    start = source.index("# >>> GENERATED EXPECTATIONS")
    start = source.index("\n", start) + 1
    end = source.index("# <<< GENERATED EXPECTATIONS")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source[:start] + literal + "\n" + source[end:])
    print("Stored %d KiB of expected answers in %s" % (len(blob) // 1024, os.path.basename(path)))


# ---------------------------------------------------------------------------
# What students call from the notebook
# ---------------------------------------------------------------------------

LAST_RESULTS: Dict[int, Dict[str, Any]] = {}


def check(task: int, namespace: Optional[Dict[str, Any]] = None) -> None:
    """Run the tests of one task against the code in your notebook."""
    if namespace is None:
        namespace = sys._getframe(1).f_globals
    sb = start(quiet=True)
    expected = practice_expectations(sb)
    workdir = tempfile.mkdtemp(prefix="ir-check-")
    try:
        with _only_html_parser():
            result = run_task(task, namespace, sb, expected, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    LAST_RESULTS[task] = result
    print(format_report(result))


def check_all(namespace: Optional[Dict[str, Any]] = None) -> None:
    """Run every task against the code in your notebook."""
    if namespace is None:
        namespace = sys._getframe(1).f_globals
    results = []
    for task in sorted(_CHECKS):
        check(task, namespace)
        results.append(LAST_RESULTS[task])
        print("")
    print("Total on the practice site: %d/100" % total_score(results))


def grade_module(module_path: str, tasks: Iterable[int] = (1, 2, 3, 4, 5), reference: Optional[str] = None,
                 timeout: float = 900, log_path: Optional[str] = None,
                 variant_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Run the tests on a python file in a separate process and return the results."""
    tasks = list(tasks)
    workdir = tempfile.mkdtemp(prefix="ir-run-")
    out_path = os.path.join(workdir, "results.jsonl")
    command = [sys.executable, os.path.abspath(__file__), "run", "--module", os.path.abspath(module_path),
               "--out", out_path, "--tasks", ",".join(str(task) for task in tasks)]
    if reference:
        command += ["--reference", os.path.abspath(reference)]
    if variant_file:
        command += ["--variant-file", os.path.abspath(variant_file)]
    log_file = open(log_path or os.path.join(workdir, "output.log"), "w", encoding="utf-8", errors="replace")
    stopped = ""
    try:
        subprocess.run(command, stdout=log_file, stderr=subprocess.STDOUT, timeout=timeout, cwd=workdir)
    except subprocess.TimeoutExpired:
        stopped = "the whole run took more than %d seconds and was stopped" % timeout
    finally:
        log_file.close()
    results = _read_results(out_path, tasks, stopped)
    shutil.rmtree(workdir, ignore_errors=True)
    return results


def _read_results(path: str, tasks: List[int], stopped: str = "") -> List[Dict[str, Any]]:
    finished: Dict[int, Dict[str, Any]] = {}
    partial: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    import_error = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if record["kind"] == "task":
                    finished[record["result"]["task"]] = record["result"]
                elif record["kind"] == "check":
                    partial[record["task"]].append(record["check"])
                elif record["kind"] == "import_error":
                    import_error = record["message"]
    results = []
    for task in tasks:
        if task in finished:
            results.append(finished[task])
            continue
        done = partial.get(task, [])
        names = {check["name"] for check in done}
        reason = import_error or stopped or "the grading process stopped here (crash or time limit)"
        for spec in _CHECKS[task]:
            if spec["name"] not in names:
                done.append({"name": spec["name"], "title": spec["title"], "points": 0, "max": spec["points"],
                             "message": reason, "seconds": 0})
        results.append({"task": task, "title": TASK_TITLES[task], "points": round(sum(c["points"] for c in done), 2),
                        "max": TASK_POINTS[task], "checks": done, "note": ""})
    return results


def check_notebook(path: str, check_name: bool = True) -> List[Dict[str, Any]]:
    """Grade a saved notebook the way the teaching team will grade it."""
    path = os.path.abspath(path)
    print("Checking %s" % os.path.basename(path))
    if not os.path.exists(path):
        print("There is no such file. Save the notebook first and pass its exact file name.")
        return []
    if check_name and check_file_name(path) is None:
        print("The file name must be your Innopolis email plus .ipynb, for example i.ivanov@innopolis.university.ipynb.")
        print("A wrong file name means 0 points for the whole homework.")
    try:
        code, notes = extract_notebook(path)
    except ValueError as exc:
        print("This file cannot be read: %s" % exc)
        return []
    for note in notes:
        print("Note: %s" % note)
    missing = sorted(name for name in _ALL_REQUIRED_NAMES if not re.search(r"\b(def|class)\s+%s\b" % name, code))
    if missing:
        print("Note: these names are not defined anywhere in the notebook: %s" % ", ".join(missing))
    workdir = tempfile.mkdtemp(prefix="ir-notebook-")
    module_path = os.path.join(workdir, "submission.py")
    with open(module_path, "w", encoding="utf-8") as handle:
        handle.write(code)
    print("")
    try:
        results = grade_module(module_path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    for result in results:
        print(format_report(result))
        print("")
    print("Total on the practice site: %d/100" % total_score(results))
    print("The real grade uses the same tests plus a short interview about your code.")
    return results


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------

def _cli_run(args: argparse.Namespace) -> None:
    tasks = [int(task) for task in args.tasks.split(",") if task.strip()]
    out_path = os.path.abspath(args.out)
    module_path = os.path.abspath(args.module)
    workdir = tempfile.mkdtemp(prefix="ir-task-")
    os.chdir(workdir)
    if args.variant_file:
        variant = load_variant(args.variant_file)
        sb = Sandbox(Site(variant.THEME, variant.TABLES))
        expected = decode_expectations(variant.EXPECTED, sb)
    else:
        sb = Sandbox(Site(PRACTICE_THEME, PRACTICE_TABLES))
        expected = practice_expectations(sb)
    reference = _load_module(os.path.abspath(args.reference), "reference_solution") if args.reference else None
    out = open(out_path, "w", encoding="utf-8")

    def emit(kind: str, payload: Dict[str, Any]) -> None:
        out.write(json.dumps({"kind": kind, **payload}) + "\n")
        out.flush()

    namespace: Dict[str, Any] = {}
    import_error = ""
    if not os.path.exists(module_path):
        import_error = "there is no file at %s, so there was nothing to grade" % module_path
    else:
        try:
            with _time_limit(30):
                module = _load_module(module_path)
            namespace = module.__dict__
        except CheckTimeout:
            import_error = "importing your code took more than 30 seconds"
        except BaseException as exc:
            where = ""
            frames = [frame for frame in traceback.extract_tb(exc.__traceback__)
                      if os.path.abspath(frame.filename) == module_path]
            if frames:
                where = " at the line: %s" % (frames[-1].line or "").strip()[:100]
            import_error = "your code could not be imported, it raised %s: %s%s" % (
                type(exc).__name__, str(exc)[:200], where)
            if isinstance(exc, ImportError):
                import_error += (". If this is a library you are allowed to use, install it for this python: "
                                 "python -m pip install requests beautifulsoup4")
    if import_error:
        emit("import_error", {"message": import_error})
        for task in tasks:
            checks = [{"name": spec["name"], "title": spec["title"], "points": 0, "max": spec["points"],
                       "message": import_error, "seconds": 0} for spec in _CHECKS[task]]
            emit("task", {"result": {"task": task, "title": TASK_TITLES[task], "points": 0,
                                     "max": TASK_POINTS[task], "checks": checks, "note": import_error}})
    else:
        with _only_html_parser():
            for task in tasks:
                result = run_task(task, namespace, sb, expected, os.path.join(workdir, "task%d" % task),
                                  student_file=module_path, reference=reference,
                                  emit=lambda check, task=task: emit("check", {"task": task, "check": check}))
                emit("task", {"result": result})
    emit("done", {})
    out.close()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)


def main(argv: Optional[List[str]] = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(description="Practice website and self-check for IR Homework 1")
    commands = parser.add_subparsers(dest="command")

    serve = commands.add_parser("serve", help="start the practice website and keep it running")
    serve.set_defaults(handler=lambda args: _cli_serve())

    check_cmd = commands.add_parser("check", help="grade a saved notebook")
    check_cmd.add_argument("notebook")
    check_cmd.set_defaults(handler=lambda args: check_notebook(args.notebook))

    run_cmd = commands.add_parser("run", help="internal: run the tests on a python file")
    run_cmd.add_argument("--module", required=True)
    run_cmd.add_argument("--out", required=True)
    run_cmd.add_argument("--tasks", default="1,2,3,4,5")
    run_cmd.add_argument("--reference", default=None)
    run_cmd.add_argument("--variant-file", default=None)
    run_cmd.set_defaults(handler=_cli_run)

    expectations = commands.add_parser("expectations", help="teaching team: rebuild the expected answers")
    expectations.add_argument("--reference", required=True)
    expectations.add_argument("--variant-file", default=None, help="build the answers for a hidden site instead")
    expectations.add_argument("--write", action="store_true")
    expectations.set_defaults(handler=lambda args: _write_expectations(args.reference, args.variant_file))

    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return
    args.handler(args)


def _cli_serve() -> None:
    sb = start()
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sb.stop()


if __name__ == "__main__":
    main()
