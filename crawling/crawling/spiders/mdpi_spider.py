import logging
import re

from bs4 import BeautifulSoup
from crawling.spiders.article_spider import ArticlesSpider

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')  # the sum of two regexes is a regex
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")
CURRPG_REG = re.compile(r"page_no=([0-9]+)&?")


class MdpiSpider(ArticlesSpider):
    name = "mdpi"
    allowed_domains = ["www.mdpi.com"]
    shorten_doi = lambda self, doi: doi.split('/')[-1]
    base_url = "https://www.mdpi.com"
    search_query = "/search?page_count=10&article_type=research-article"

    def __init__(self, dump_dir=None, year_from=None, year_to=None,
                       start_page=None, stop_page=None, journal=None,
                       update = "no",
                       name=None, **kwargs): 
        if year_from is not None:
            self.search_query += "&year_from=" + year_from
        if year_to is not None:
            self.search_query += "&year_to=" + year_to
        if journal is not None:
            self.search_query += "&journal=" + journal
        self.search_query += "&page_no="
        super().__init__(dump_dir, start_page, stop_page, update, name, **kwargs)

            
    def parse_searchpage(self, response):
        articles = response.css('div.article-content a.title-link')
        yield from response.follow_all(articles, self.parse_article)
        
    def learn_search_pages(self, response):
        soup = BeautifulSoup(response.text, 'lxml')
        hit = soup.find(text=SEARCH_PAGES_PATTERN)
        if hit is not None:
            res = int(re.findall(r"\d+", hit)[-1])
            self.log(f"It seems there are {res} search pages for this query.")
            return res
        else:
            return None

    def parse_article(self, response) -> dict:
        soup = BeautifulSoup(response.text, 'lxml')
        
        metadata = {}
        metadata['title'] = soup.find('meta', {'name': 'title'}).get('content').strip()

        metadata['url'] = soup.find('meta', {'property': 'og:url'}).get('content').strip()

        metadata['authors'] = [x.get('content') for x in soup.findAll('meta', {"name": "citation_author"})]

        journal_dict = {'abbrev': soup.find('a', {'class': "Var_JournalInfo"}).get('href').split('/')[2],
                        'title': soup.find('meta', {'name': "citation_journal_title"}).get('content'), 'volume': int(soup.find('meta', {'name': "citation_volume"}).get('content'))}
        issue = soup.find('meta', {'name': "citation_issue"})
        if issue is not None:
            journal_dict['issue'] = issue.get('content')
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
        metadata['doi'] = DOI_PATTERN.search(bib_identity.getText()).group()[16:]
        metadata['doi_registered'] = UNREGISTERED_DOI_PATTERN.search(bib_identity.getText()) is None  # unregistered DOI probably means that the article is in early access

        find = soup.find('a', {'href': lambda x: x is not None and x.endswith('review_report')})
        if find is None:
            # article has no open access reviews
            metadata['has_reviews'] = False
        else:
            metadata['has_reviews'] = True
            # warning: this found url may point to the same url as the article
            # (it could end with #review_report) in which case reviews should be parsed differently
            
            # TODO check if all mdpi articles have this url format
            metadata['reviews_url'] = self.base_url + find['href']

        if self.dump_dir is not None:
            self.dump_metadata(metadata, self.shorten_doi(metadata['doi']))
        
        return metadata
