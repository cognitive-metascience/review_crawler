"""
test crawler for the MDPI database.
goes through first 3 pages of search results = 30 articles and dumps files in scraped/mdpi/articles
"""
import logging
import os
import json
import re
from typing import Union

import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time

BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&view=compact"

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')  # the sum of two regexes is a regex
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")

# for logging:
logs_path = os.path.join(os.path.dirname(__file__), 'logs')
runtime_dirname = '_'.join(time.ctime().split(' ')[1:4]).replace(':', '_')
log_filename = runtime_dirname + ".log"
logger = logging.getLogger("logger")
logging_file_handler = logging.FileHandler(os.path.join(logs_path, log_filename))
logging_file_handler.formatter = logging.Formatter('%(asctime)s|%(levelname)s:%(message)s|', '%d/%m/%Y %H:%M:%S')
logger.addHandler(logging_file_handler)
logging_stream_handler = logging.StreamHandler()
logging_stream_handler.setLevel(logging.WARNING)
logger.addHandler(logging_stream_handler)


def _cook(url: str) -> Union[BeautifulSoup, None]:
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup


def _shorten(uri: str) -> str:
    if DOI_PATTERN.match(uri): return uri.split('/')[-1]
    elif uri.startswith('https://www.mdpi.com/'): return '_'.join(uri.split('/')[-4:])
    else: return uri


def learn_search_pages(url):
    """
    Looks into a Soup and figures out how many search pages were returned after searching the MDPI database.

    :param url: url that should contain search results.
    :type url: str
    :rtype: int
    """
    soup = _cook(url)
    if not url.startswith("https://www.mdpi.com/search?"):
        raise Exception("Invalid url for learn_search_pages:", url)
    hit = soup.find(text=SEARCH_PAGES_PATTERN)
    assert hit is not None  # will pass unless something very strange happened
    return int(re.findall(r"\d+", hit)[-1])


def learn_journals(soup):
    """
    Looks into a Soup and figures out what journals are in MDPI's database.
    # todo: change parameter to url


    :type soup: BeautifulSoup
    :return: a dict of keys: journal's abbreviation; and values: journa's full title
    :rtype: dict
    """
    journals = {i['value']: i.text.strip() for i in list(soup.find('select', {"id": "journal", "class": "chosen-select"}).findAll('option'))[1:]}
    assert journals is not None  # will pass unless perhaps the mdpi changed their website layout
    return journals


def parse_article(url, dump_dir=None):
    """
    Parses an MDPI article with the given url. Saves output to a JSON file if dump_dir is specified.

    :type dump_dir: str
    :type url: str
    :return: dict containing scraped metadata
    :rtype: dict
    """

    if not url.startswith("https://www.mdpi.com/"):
        raise Exception("Invalid url for parse_article.")

    metadata = {}
    logger.info(f"Parsing: {_shorten(url)}.", end=" | ")

    try:
        soup = _cook(url)
        metadata['title'] = soup.find('meta', {'name': 'title'}).get('content').strip()
        logger.info(f"Title: {metadata['title']}", end=' | ')

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
        logger.warning(f"There was a problem with article from {_shorten(url)}: {e}\narticle metadata: {metadata}")

    else:
        logger.info(f"Parsed {_shorten(url)} succesfully.", end=" | ")
        if dump_dir is not None:
            logger.info("Saving to file.", end=" | ")
            filename = f"{os.path.join(dump_dir, _shorten(url))}.json"
            if os.path.exists(filename):
                logger.warning(f"Warning! {_shorten(url)}.json already exists in dump_dir. Will NOT overwrite.", end=" | ")
            else:
                with open(filename, 'w+', encoding="utf-8") as fp:
                    json.dump(metadata, fp, ensure_ascii=False)
                logger.info(f"Saved metadata to file.", end=" | ")
    return metadata


def page_crawl(url, dump_dir=None):
    """
    Crawls through a single page of MDPI search results. It's able to get 15 at most.

    :param url: Webpage with certain search results.
    :type url: str
    :param dump_dir: if specified, will dump parsed metadata to JSON files in dump_dir.
    :type dump_dir: path-like
    :return: A list of dicts containing metadata of found articles.
    :rtype: list
    """

    if not url.startswith("https://www.mdpi.com/search?"):
        raise Exception("Invalid url for page_crawl.")

    scraped_articles = []

    soup = _cook(url)
    logger.info(f"Crawling through search page: {url.split('&')[-1]}.")

    # iterate over all article-content divs on the page to find urls
    article_divs = soup.findAll('div', {'class': 'article-content'})
    for div in article_divs:
        a_title = div.find('a', {'class': 'title-link'})
        scraped_articles.append(parse_article(url=BASE_URL + a_title.get('href'), dump_dir=dump_dir))
    logger.info(f"Finished with {url.split('&')[-1]}.")

    return scraped_articles


def crawl(max_articles=None, dump_dir=None, make_logs=False):
    """
    Crawls through the MDPI database, dumping scraped article metadata into json files.
    Provide a path to a directory if you want to save metadata to json files.

    :param dump_dir: path do directory in which json files will be dumped.
    :type dump_dir: str
    :param max_articles:
    :type max_articles: int
    :param make_logs: set this flag to True if you want to see logfiles generated in the working directory.
    :type make_logs: bool
    :return: a list of dicts containing metadata of found articles.
    :rtype: list
    """

    if dump_dir is not None and not os.path.exists(os.path.realpath(dump_dir)):
        logger.info("dump_dir does not exist. Will create.")
        os.makedirs(dump_dir)

    if make_logs:
        logger.setLevel(logging.DEBUG)
        if not os.path.exists(logs_path):
            os.makedirs(logs_path)

    if max_articles is None:
        pages_count = learn_search_pages(BASE_SEARCH_URL)
    else:
        pages_count = int(max_articles / 10)

    scraped_articles = []
    done_pages_counter = 0
    errors_counter = 0

    # using threading to crawl trough many search pages at once.
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []

        # for i in range(4800, 4900):
        for i in range(pages_count):
            try:
                futures.append(executor.submit(page_crawl, url=f"{BASE_SEARCH_URL}&page_no={i + 1}", dump_dir=dump_dir))
            except Exception as e:
                logging.getLogger('logger').exception(e)

        for future in concurrent.futures.as_completed(futures):
            if future.exception:
                errors_counter += 1
                logging.getLogger('logger').exception(future.exception(), exc_info=False)
            else:
                scraped_articles += (future.result())
                done_pages_counter += 1
                logger.info(f"{done_pages_counter} pages crawled.")

    print("Done crawling through MDPI.")
    print("Total number of scraped articles: ", len(scraped_articles))
    print(f"Number of errors while crawling: {errors_counter}")
    logger.info("Cleaning log folder.")
    for path in os.listdir(logs_path):
        if os.path.isdir(os.path.join(logs_path, path)) and len(os.listdir((os.path.join(logs_path, path)))) == 0:
            os.rmdir((os.path.join(logs_path, path)))
    if len(os.listdir(logs_path)) == 0:
        os.rmdir(logs_path)

    return scraped_articles


if __name__ == '__main__':
    startime = time.process_time()
    scraped = crawl(dump_dir="scraped/mdpi/articles",
                    max_articles=30,  # delete this line to crawl everything
                    make_logs=True)
    runtime = time.process_time() - startime
    print(f"and it all took {runtime} seconds.")
    # with open("scraped_mdpi_articles_metadata.json", 'w+', encoding="utf-8") as fp:
    #     json.dump(scraped, fp)

    print(f"Number of reviewed articles found: {len([a for a in scraped if a['has_reviews']])}")
