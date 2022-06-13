import json
import os
import re
from bs4 import BeautifulSoup
import scrapy


# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')  # the sum of two regexes is a regex
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")


# globals:
BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&page_no="

# regex patterns
currpg_reg = re.compile(r"page_no=([0-9]+)&?")



class MdpiSpider(scrapy.Spider):
    name = 'mdpi'
    allowed_domains = ['www.mdpi.com']

    def __init__(self, start_page=None, dump_dir=None, journal=None, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.logger.info(f"Setting up a MDPIcrawler. start_page={start_page}, dump_dir={dump_dir}")
        if dump_dir is None:
            self.logger.warning("dump_dir is None. Output is not saved to files.")

        if start_page is not None:
            self.start_urls = [BASE_SEARCH_URL + str(start_page)]
            self.start_page = start_page
        else:
            self.start_urls = [BASE_SEARCH_URL + "1"]
            self.start_page = 1

    def parse(self, response):
        for i in range(self.start_page, self.learn_search_pages(response.text)):
            page = BASE_SEARCH_URL + str(i+1)
            yield response.follow(page, callback=self.parse_searchpage)

    def parse_searchpage(self, response):
        articles = response.css('div.article-content a.title-link')
        yield from response.follow_all(articles, self.parse_article)
        
    def parse_article(self, response):
        metadata = self.get_metadata_from_html(response.text)
        
        if metadata['has_reviews']:
            a_short_doi = response.url.split['/'][-1]
            self.logger.info(f'Article {a_short_doi} probably has reviews!')
            yield response.follow(metadata['reviews_url'], self.parse_reviews)

            if self.dump_dir is not None:
               self.dump_metadata(metadata, a_short_doi)

        yield metadata

    def parse_reviews(self, response):
        # TODO
        metadata = {}

        if self.dump_dir is not None:
            a_short_doi = response.url.split['/'][-1]
            self.dump_metadata(metadata, a_short_doi, 'reviews')

        yield metadata

    def dump_metadata(self, metadata, dirname=None, filename='metadata'):
        if dirname is None:
            dirpath = self.dump_dir
        else:
            dirpath = os.path.join(self.dump_dir, dirname)
        os.makedirs(dirpath, exist_ok=True)
        self.logger.debug(f"Saving metadata to file in {dirpath}.")
        try:
            filepath = f"{os.path.join(dirpath, filename)}.json"
            if os.path.exists(filepath):
                self.logger.warning(f"metadata already exists in {dirpath}. Will overwrite.")
            with open(filepath, 'w+', encoding="utf-8") as fp:
                json.dump(metadata, fp, ensure_ascii=False)
        except Exception as e:
            self.logger.exception(f"Problem while saving to file: {filepath}.\n{e}")
        else:
            self.logger.debug(f"Saved metadata to file.")

    def learn_search_pages(self, html):
        soup = BeautifulSoup(html, 'lxml')
        hit = soup.find(text=SEARCH_PAGES_PATTERN)
        if hit is not None:
            return int(re.findall(r"\d+", hit)[-1])
        else:
            return None

    def get_metadata_from_html(self, html: str) -> dict:
        soup = BeautifulSoup(html, 'lxml')
        
        metadata = {}
        metadata['title'] = soup.find('meta', {'name': 'title'}).get('content').strip()

        metadata['url'] = soup.find('meta', {'property': 'og:url'}).get('content').strip()

        metadata['authors'] = [x.get('content') for x in soup.findAll('meta', {"name": "citation_author"})]

        journal_dict = {'abbrev': soup.find('a', {'class': "Var_JournalInfo"}).get('href').split('/')[2],
                        'title': soup.find('meta', {'name': "citation_journal_title"}).get('content'), 'volume': int(soup.find('meta', {'name': "citation_volume"}).get('content'))}
        issue = soup.find('meta', {'name': "citation_issue"})
        if issue is not None:
            journal_dict['issue'] = int(issue.get('content'))
        metadata['journal'] = journal_dict

        pubdate_string = soup.find('meta', {'name': 'citation_publication_date'}).get('content')
        metadata['publication_date'] = {'year': int(pubdate_string.split('/')[0]), 'month': int(pubdate_string.split('/')[1])}

        metadata['retracted'] = RETRACTION_PATTERN.search(soup.getText()) is not None

        keywords = soup.find('span', {'itemprop': 'keywords'})
        if keywords is not None:
            metadata['keywords'] = keywords.getText().strip().split('; ')
        else:
            metadata['keywords'] = []

        pdf_tag = soup.find('meta', {'name': 'fulltext_pdf'})
        if pdf_tag is not None:
            metadata['fulltext_pdf_url'] = pdf_tag.get('content')
        xml_tag = soup.find('meta', {'name': 'fulltext_xml'})
        if xml_tag is not None:
            metadata['fulltext_xml_url'] = xml_tag.get('content')
        html_tag = soup.find('meta', {'name': 'fulltext_html'})
        if html_tag is not None:
            metadata['fulltext_html_url'] = html_tag.get('content')

        bib_identity = soup.find('div', {'class': 'bib-identity'})
        metadata['doi'] = DOI_PATTERN.search(bib_identity.getText()).group()
        metadata['doi_registered'] = UNREGISTERED_DOI_PATTERN.search(bib_identity.getText()) is None  # unregistered DOI probably means that the article is in early access

        if soup.find('a', {'href': lambda x: x is not None and x.endswith('review_report')}) is None:
            # article has no open access reviews
            metadata['has_reviews'] = False
        else:
            metadata['has_reviews'] = True
            metadata['reviews_url'] = metadata['url'] + "/review_report"

        return metadata

        # todo: parse more metadata, parse reviews

            