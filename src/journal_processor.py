"""
Journal processing module for RSS feed parsing and abstract extraction.

This module handles:
- Loading journal lists from configuration
- Parsing RSS/Atom feeds
- Extracting abstracts from journal websites
- Extracting keywords from papers
"""

import feedparser
import logging
import re
import time
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any, List, Iterable

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "radiation therapy", "radiotherapy", "dose", "dosimetry", "treatment planning",
    "IMRT", "VMAT", "stereotactic", "brachytherapy", "Monte Carlo", "CT", "MRI",
    "linear accelerator", "beam", "phantom", "QA", "quality assurance", "IGRT",
    "patient safety", "machine learning", "AI", "deep learning", "proton therapy",
    "imaging", "segmentation", "contouring", "organ at risk", "OAR", "PTV", "GTV"
]

class JournalProcessor:
    """
    Processor for journal RSS feeds and paper metadata extraction.

    Handles RSS feed parsing, abstract extraction from journal websites,
    and keyword extraction based on medical physics terminology.
    """

    def __init__(self, config):
        """
        Initialize journal processor with configuration.

        Args:
            config: Configuration dictionary containing journal settings
        """
        self.cfg = config
        self.request_delay = self.cfg.get('journals', {}).get('request_delay', 1)
        self.timeout = self.cfg.get('journals', {}).get('timeout', 30)
        self.user_agent = self.cfg.get('journals', {}).get('user_agent', 'PaperSummarizer/1.0')
        self.max_papers = self.cfg.get('journals', {}).get('max_papers_per_journal', 50)
        self.extractors = self.cfg.get('journals', {}).get('extractors', {})
        self.keywords_enabled = self.cfg.get('keywords', {}).get('enabled', True)
        self.keyword_max = self.cfg.get('keywords', {}).get('max_count', 5)
        custom_terms = self.cfg.get('keywords', {}).get('custom_terms', []) or []
        self.keyword_terms = [*DEFAULT_KEYWORDS, *custom_terms]
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': self.user_agent})

    def load_journals(self, list_file: str) -> Dict[str, str]:
        """
        Load journal names and RSS feed URLs from file.

        Args:
            list_file: Path to journal list file (name on one line, URL on next)

        Returns:
            Dictionary mapping journal names to RSS feed URLs
        """
        journals = {}
        try:
            with open(list_file, 'r', encoding='utf-8') as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]
            for i in range(0, len(lines), 2):
                if i + 1 < len(lines):
                    journals[lines[i]] = lines[i+1]
        except FileNotFoundError:
            logger.warning(f"Journal list file not found: {list_file}; using embedded defaults")
            journals = {
                "Medical Dosimetry": "http://www.meddos.org/current.rss",
                "Physica Medica": "http://www.physicamedica.com/current.rss",
                "Journal of Applied Clinical Medical Physics": "https://aapm.onlinelibrary.wiley.com/feed/15269914/most-recent",
                "Medical Physics": "https://aapm.onlinelibrary.wiley.com/feed/24734209/most-recent",
                "Physics in Medicine and Biology": "https://iopscience.iop.org/journal/rss/0031-9155",
                "International Journal of Radiation Oncology, Biology, Physics": "https://www.redjournal.org/current.rss",
                "Radiation Oncology": "http://www.ro-journal.com/latest/rss"
            }
        return journals

    def parse_feed(self, url: str):
        feed = feedparser.parse(url)
        return feed.entries[: self.max_papers]

    def extract_keywords(self, title: str, abstract: str) -> List[str]:
        if not self.keywords_enabled:
            return []
        combined = (title + ' ' + abstract).lower()
        found = [kw for kw in self.keyword_terms if kw.lower() in combined]
        return found[: self.keyword_max]

    def extract_paper_info(self, entry, journal_url: str) -> Dict[str, str]:
        title = entry.get('title', '제목 없음')
        link = entry.get('link', '')
        published = entry.get('published', '') or entry.get('updated', '')
        abstract = entry.get('summary', '') or ''
        if not abstract and link:
            abstract = self._extract_abstract_from_page(link, journal_url)
        if abstract:
            abstract = re.sub(r'<.*?>', '', abstract).strip()
        return {
            'title': title,
            'link': link,
            'published': published,
            'abstract': abstract
        }

    def _extract_abstract_from_page(self, link: str, journal_url: str) -> str:
        """
        Extract abstract from journal article webpage.

        Args:
            link: URL of the article
            journal_url: RSS feed URL to determine which extractor to use

        Returns:
            Extracted abstract text or empty string if extraction fails
        """
        domain_key = None
        for key in self.extractors:
            if key in journal_url:
                domain_key = key
                break
        if not domain_key:
            logger.debug(f"No extractor for journal: {journal_url}")
            return ''

        extractor = self.extractors[domain_key]
        try:
            resp = self.session.get(link, timeout=self.timeout)
            soup = BeautifulSoup(resp.text, 'html.parser')
            selector = extractor.get('selector', '')
            etype = extractor.get('type', 'class')

            # Robust selector parsing
            elem = None
            if etype == 'class':
                # Remove 'div.' prefix if present, otherwise use as-is
                class_name = selector.replace('div.', '', 1) if selector.startswith('div.') else selector
                elem = soup.find('div', class_=class_name)
            elif etype == 'id':
                # Remove 'div#' prefix if present, otherwise use as-is
                id_name = selector.replace('div#', '', 1) if selector.startswith('div#') else selector
                elem = soup.find('div', id=id_name)
            else:
                # Fallback: use CSS selector directly
                elem = soup.select_one(selector)

            if elem:
                return elem.get_text().strip()
        except Exception as e:
            logger.warning(f"Abstract extraction failed for {link}: {e}")
        return ''

    def iter_papers(self, journal_name: str, journal_url: str):
        entries = self.parse_feed(journal_url)
        total = len(entries)
        logger.info(f"{journal_name}: 총 {total}개 항목")
        for idx, entry in enumerate(entries, 1):
            logger.info(f"{journal_name}: {idx}/{total} 처리 중")
            yield entry
            time.sleep(self.request_delay)
