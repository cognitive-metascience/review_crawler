"""
test crawler for the MDPI database.
goes through first 3 pages of search results = 30 articles and dumps files in scraped/mdpi/articles
"""
import logging
import os
import json
import re
import concurrent.futures
import time

import requests
from review_crawler.utils import cook_from_html

from utils import cook, get_logger ,clean_log_folder


# globals:
BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&view=compact"

crawler_dir = os.path.dirname(__file__)

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
logger: logging.Logger
logger = get_logger("mdpiLogger")

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')  # the sum of two regexes is a regex
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")



def _shorten(url: str) -> str:
    if DOI_PATTERN.match(url): return url.split('/')[-1]
    elif url.startswith('https://www.mdpi.com/'): return '_'.join(url.split('/')[-4:])
    else: return url


def learn_search_pages(url):
    """
    Looks into a Soup and figures out how many search pages were returned after searching the MDPI database.

    :param url: url that should contain search results.
    :type url: str
    :rtype: int
    """
    soup = cook(url)
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

def get_metadata_from_html(html: str) -> dict:
    soup = cook_from_html(html)
    
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

    logger.info(f"Parsing: {url}.")

    try:
        metadata = get_metadata_from_html(requests.get(url).content)
        
    except Exception as e:
        logger.warning(f"There was a problem parsing article from {_shorten(url)}: {e}\narticle metadata: {metadata}")
        raise e

    else:
        # save metadata to file:
        logger.info(f"Parsed {_shorten(url)} succesfully.")
        if dump_dir is not None:
            logger.info("Saving to file.")
            try:
                filename = f"{os.path.join(dump_dir, _shorten(url))}.json"
                if os.path.exists(filename):
                    logger.warning(f"{_shorten(url)}.json already exists in dump_dir. Will NOT overwrite.")
                else:
                    with open(filename, 'w+', encoding="utf-8") as fp:
                        json.dump(metadata, fp, ensure_ascii=False)
            except Exception as e:
                logger.exception(f"Problem while saving to file: {filename}.\n{e}")
            else:
                logger.info(f"Saved metadata to file.")
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

    logger.info(f"Trying to crawl through search page: {url.split('&')[-1]}.")
    soup = cook(url)

    # iterate over all article-content divs on the page to find urls 
    # todo: and DOIs
    article_divs = soup.findAll('div', {'class': 'article-content'})
    for div in article_divs:
        a_title = div.find('a', {'class': 'title-link'})
        try:
            scraped_articles.append(parse_article(url=BASE_URL + a_title.get('href'), dump_dir=dump_dir))
        except Exception as e:
            raise e # todo: better error handling here
    logger.info(f"Finished with {url.split('&')[-1]}.")

    return scraped_articles


def crawl(max_articles=None, dump_dir=None, print_logs=False):
    """
    Crawls through the MDPI database, dumping scraped article metadata into json files.
    Provide a path to a directory if you want to save metadata to json files.

    :param dump_dir: path do directory in which json files will be dumped.
    :type dump_dir: str
    :param max_articles:
    :type max_articles: int
    :param print_logs: set this flag to True if you want to see logfiles generated in the working directory.
    :type print_logs: bool
    :return: a list of dicts containing metadata of found articles.
    :rtype: list
    """

    if print_logs:
        logger.parent.handlers[0].setLevel(logging.INFO)

    logger.debug(f"Setting up a MDPIcrawler. max_articles={max_articles}, dump_dir={dump_dir}")
    if dump_dir is None:
        logger.warning("dump_dir is None. Output is not saved to files.")

    if dump_dir is not None and not os.path.exists(os.path.realpath(dump_dir)):
        logger.info("dump_dir does not exist. Will create.")
        os.makedirs(dump_dir)

    max_articles = None
    if max_articles is None:
        pages_count = learn_search_pages(BASE_SEARCH_URL)
    else:
        pages_count = int(max_articles / 10)

    scraped_articles = []
    done_pages_counter = 0
    errors_counter = 0

    logger.debug("Finished crawler setup.")

    # using threading to crawl trough many search pages at once.
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []

        # for i in range(4800, 4900):
        for i in range(pages_count):
            try:
                futures.append(executor.submit(page_crawl, url=f"{BASE_SEARCH_URL}&page_no={i + 1}", dump_dir=dump_dir))
            except Exception as e:
                logger.exception(e)

        for future in concurrent.futures.as_completed(futures):
            e = future.exception()
            if e:
                errors_counter += 1
                logger.error(e)
            else:
                scraped_articles += (future.result())
                done_pages_counter += 1
                logger.info(f"{done_pages_counter} pages crawled.")

    logger.info("Done crawling.")
    logger.info(f"Total number of scraped articles: {len(scraped_articles)}")
    logger.info(f"Number of errors while crawling: {errors_counter}")
    logger.debug("Cleaning log folder...".rstrip('\n\n'))
    clean_log_folder(logs_path)
    logger.debug("Done.")

    return scraped_articles


if __name__ == '__main__':
    startime = time.process_time()
    scraped = crawl(max_articles=10, print_logs= True)
   
    # with open("scraped_mdpi_articles_metadata.json", 'w+', encoding="utf-8") as fp:
    #     json.dump(scraped, fp)

    print(f"Number of reviewed articles found: {len([a for a in scraped if a['has_reviews']])}")
    runtime = time.process_time() - startime
    print(f"and it all took {runtime} seconds.")