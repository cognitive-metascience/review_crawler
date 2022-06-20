from io import TextIOWrapper
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
CURRPG_REG = re.compile(r"page_no=([0-9]+)&?")

# globals:
BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&page_no="

class MdpiSpider(scrapy.Spider):
    name = 'mdpi'
    allowed_domains = ['www.mdpi.com']
    shorten_doi = lambda self, doi: doi.split('/')[-1]

    def __init__(self, dump_dir=None, start_page=None, stop_page=None, journal=None, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.logger.info(f"Setting up a MdpiSpider. start_page={start_page}, stop_page={stop_page}, dump_dir={dump_dir}")
        if dump_dir is None:
            self.logger.warning("dump_dir is None. JSON files will not be saved!")
        self.dump_dir = dump_dir
        if journal is not None:
            pass    # todo     
        if start_page is not None:
            self.start_urls = [BASE_SEARCH_URL +start_page]
            self.start_page = int(start_page)
        else:
            self.start_urls = [BASE_SEARCH_URL + "1"]
            self.start_page = 1
        self.stop_page = stop_page       

    def parse(self, response):
        if self.stop_page is None:
            stop_page = int(self.learn_search_pages(response.text))
        else:
            stop_page = int(self.stop_page)

        for i in range(self.start_page, stop_page):
            page = BASE_SEARCH_URL + str(i+1)
            yield response.follow(page, callback=self.parse_searchpage)

    def parse_searchpage(self, response):
        articles = response.css('div.article-content a.title-link')
        yield from response.follow_all(articles, self.parse_article)
        
    def parse_article(self, response):
        metadata = self.get_metadata_from_html(response.text)
        
        if metadata['has_reviews']:
            a_short_doi = self.shorten_doi(metadata['doi'])
            self.logger.info(f'Article {a_short_doi} probably has reviews!')
            # yield response.follow(metadata['reviews_url'], self.parse_reviews)
            metadata['sub_articles'] = []

            if self.dump_dir is not None:
               self.dump_metadata(metadata, a_short_doi)

        yield metadata   


    def dump_metadata(self, metadata, dirname=None, filename='metadata'):
        """Takes a dictionary containing article metadata and saves it to a JSON file in `self.dump_dir`.

        Args:
            metadata (dict): dictionary to be saved to file.
            dirname (str, optional): If specified, a directory inside `self.dump_dir` will be created (if it doesn't exist) and the metadata is saved there. Defaults to None.
            filename (str, optional): Base file name (without an extension). Defaults to 'metadata'.
        """
        assert self.dump_dir is not None
        if dirname is None:
            dirpath = self.dump_dir
        else:
            dirpath = os.path.join(os.path.abspath(self.dump_dir), dirname)
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
            self.logger.info(f"Saved metadata to {dirname}/{filename}.json")

    def learn_search_pages(self, html):
        soup = BeautifulSoup(html, 'lxml')
        hit = soup.find(text=SEARCH_PAGES_PATTERN)
        if hit is not None:
            res = int(re.findall(r"\d+", hit)[-1])
            self.log(f'It seems there are {res} search pages for this query.')
            return res
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

        find = soup.find('a', {'href': lambda x: x is not None and x.endswith('review_report')})
        if find is None:
            # article has no open access reviews
            metadata['has_reviews'] = False
        else:
            metadata['has_reviews'] = True
            # warning: this found url may point to the same url as the article
            # (it could end with #review_report) in which case reviews should be parsed differently
            metadata['reviews_url'] = metadata['url'] + find['href']

        return metadata
