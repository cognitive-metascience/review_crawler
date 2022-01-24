"""
test crawler for the MDPI database.
goes through first 2 pages of search results = 20 articles and dumps files in scraped/mdpi/articles
"""
import logging
import os
import json
import re
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time

BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&view=compact"

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')    # the sum of two regexes is a regex
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")

# for logging:
logs_path = os.path.join(os.path.dirname(__file__), 'logs')
runtime_dirname = '_'.join(time.ctime().split(' ')[1:4]).replace(':', '_')


def _cook(url: str) -> BeautifulSoup: return BeautifulSoup(requests.get(url).content, 'lxml')


def _shorten(doi: str) -> str: return doi.split('/')[-1]


def learn_search_pages(search_soup):
    """
    Looks into a Soup and figures out how many search pages were returned after searching the MDPI database.

    :type search_soup: BeautifulSoup
    :rtype: int
    """

    hit = search_soup.find(text=SEARCH_PAGES_PATTERN)
    assert hit is not None  # will pass unless something very strange happened
    return int(re.findall(r"\d+", hit)[-1])


def learn_journals(soup):
    """
    Looks into a Soup and figures out what journals are in MDPI's database.


    :type soup: BeautifulSoup
    :return: a dict of keys: journal's abbreviation; and values: journa's full title
    :rtype: dict
    """
    journals = {i['value']: i.text.strip() for i in list(soup.find('select', {"id": "journal", "class": "chosen-select"}).findAll('option'))[1:]}
    assert journals is not None  # will pass unless perhaps the mdpi changed their website layout
    return journals


def parse_article(doi, url=None, dump_dir=None):
    """
    Parses an MDPI article with the given url. Saves output to a JSON file if dump_dir is specified.

    :type dump_dir: str
    :type url:
    :return: dict containing scraped metadata
    :rtype: dict
    """

    if not url.startswith("https://www.mdpi.com/"):
        raise Exception("Invalid url for parse_article.")

    metadata = {}
    # parsing
    try:
        soup = _cook(url)
        metadata['title'] = soup.find('meta', {'name': 'title'}).get('content').strip()
        print(f"| Parsing: {metadata['title']}")

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
            metadata['reviews_url'] = url + "/review_report"

    # todo: more metadata, parse reviews

    except Exception as e:
        print("There's a problem with this article:", metadata)  # todo: better error logging
        log_filename = _shorten(doi) + ".log"
        logger = logging.getLogger("logger")
        logger.addHandler(logging.FileHandler(os.path.join(logs_path, runtime_dirname, log_filename)))
        logger.error(e)
    else:
        if dump_dir is not None:
            print("| Trying to save to to file.", end=" | ")
            filename = f"{os.path.join(dump_dir, _shorten(doi))}.json"
            if os.path.exists(filename):
                print("Warning! File already exists. Will overwrite.", end=" | ")
            with open(filename, 'w+', encoding="utf-8") as fp:
                json.dump(metadata, fp, ensure_ascii=False)
            print(f"Saved metadata to {filename}. | ")

    return metadata


def page_crawl(url, dump_dir=None):
    """
    Crawls through a single page of MDPI search results. It's able to get 15 at most.

    :param dump_dir:
    :type dump_dir:
    :param url: Webpage with certain search results.
    :type url: str
    :return: A list of dicts containing metadata of found articles.
    :rtype: list
    """

    if not url.startswith("https://www.mdpi.com/search?"):
        raise Exception("Invalid url for page_crawl.")

    soup = _cook(url)

    scraped_articles = []

    # iterate over all article-content divs on the page to find urls
    article_divs = soup.findAll('div', {'class': 'article-content'})
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        for div in article_divs:
            a_title = div.find('a', {'class': 'title-link'})
            doi = DOI_PATTERN.search(div.getText()).group()
            # using threading to parse all articles on this search page at the same time
            futures.append(executor.submit(parse_article, doi=doi, url=BASE_URL + a_title.get('href'), dump_dir=dump_dir))
        for future in concurrent.futures.as_completed(futures):
            scraped_articles.append(future.result())

    # todo: implement queueing
    return scraped_articles


def crawl(dump_dir, make_logs=False):
    """
    Crawls through the MDPI database, dumping scraped article metadata into json files.
    Provide a path to a directory if you want to save metadata to json files.

    :param dump_dir: path do directory in which json files will be dumped.
    :type dump_dir: str
    :param make_logs: set this flag to True if you want to see logfiles generated in the working directory.
    :type make_logs: bool
    :return: a list of dicts containing metadata of found articles.
    :rtype: list
    """

    if not os.path.exists(os.path.realpath(dump_dir)):
        os.makedirs(dump_dir)

    log_dir = os.path.join(logs_path, runtime_dirname)
    if make_logs:
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

    soup = _cook(BASE_SEARCH_URL)

    pages_count = learn_search_pages(soup)

    scraped_articles = []

    # for i in range(pages_count):
    for i in range(2):  # change this line to the one above to crawl through everything
        searchpage_url = f"{BASE_SEARCH_URL}&page_no={i + 1}"
        print(f"Crawling through search page: {searchpage_url.split('&')[-1]}")
        scraped_articles += page_crawl(searchpage_url, dump_dir=dump_dir)
        print(f"{i + 1} search pages crawled. {len(os.listdir(dump_dir))} files in dump_dir.")

    print("Done crawling through MDPI.")
    print("Total number of scraped articles: ", len(scraped_articles))

    if make_logs:
        logfiles_count = len(os.listdir(log_dir))
        print(f"Number of errors while crawling: {logfiles_count}")

        if logfiles_count == 0:
            os.rmdir(log_dir)

    return scraped_articles


if __name__ == '__main__':
    scraped = crawl(dump_dir="scraped/mdpi/articles", make_logs=True)

    # with open("scraped_mdpi_articles_metadata.json", 'w+', encoding="utf-8") as fp:
    #     json.dump(scraped, fp)

    print(f"Number of reviewed articles found: {len([a for a in scraped if a['has_reviews']])}")
