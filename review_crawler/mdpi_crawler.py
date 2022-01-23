"""
test crawler for the MDPI database.
skonczyles na 484.
goes through first 2 pages of search results = 20 articles
currently scrapes a lot of metadata for found articles and dumps all data into a single json file
todo: save data to json files as we crawl, instead of creating a gigantic list of articles
"""

import json
import os
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&view=compact"

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
UNREGISTERED_DOI_PATTERN = re.compile(DOI_PATTERN.pattern + r'\s+\(registering\s+DOI\)')
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")
RETRACTION_PATTERN = re.compile(r"Retraction published on \d+")


def _cook(url: str) -> BeautifulSoup: return BeautifulSoup(requests.get(url).content, 'lxml')


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


def parse_article(url):
    """
    Parses an article with the givenurl.

    :type url:
    :return: dict containing scraped metadata
    :rtype: dict
    """
    if not url.startswith("https://www.mdpi.com/"):
        raise Exception("Invalid url for parse_article.")

    soup = _cook(url)
    metadata = {}

    try:
        metadata['title'] = soup.find('meta', {'name': 'title'}).get('content').strip()
        print(f"| Currently parsing: {metadata['title']}")

        metadata['url'] = soup.find('meta', {'property': 'og:url'}).get('content').strip()
        assert url == metadata['url']

        metadata['authors'] = [x.get('content') for x in soup.findAll('meta', {"name": "citation_author"})]

        jrnl_dict = {'abbrev': soup.find('a', {'class': "Var_JournalInfo"}).get('href').split('/')[2],
                     'title': soup.find('meta', {'name': "citation_journal_title"}).get('content'), 'volume': int(soup.find('meta', {'name': "citation_volume"}).get('content'))}
        issue = soup.find('meta', {'name': "citation_issue"})
        if issue is not None:
            jrnl_dict['issue'] = int(issue.get('content'))
        metadata['journal'] = jrnl_dict

        pubdate_string = soup.find('meta', {'name': 'citation_publication_date'}).get('content')
        metadata['publication_date'] = {'year': int(pubdate_string.split('/')[0]), 'month': int(pubdate_string.split('/')[1])}

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
        metadata['doi_registered'] = UNREGISTERED_DOI_PATTERN.search(bib_identity.getText()) is not None  # unregistered DOI probably means that the article is in early access
        metadata['retracted'] = RETRACTION_PATTERN.search(soup.getText()) is not None

        if soup.find('a', {'href': lambda x: x is not None and x.endswith('review_report')}) is None:
            # article has no open access reviews
            metadata['has_reviews'] = False
        else:
            metadata['has_reviews'] = True
            metadata['reviews_url'] = url + "/review_report"

    # todo: more metadata, parse reviews

    except Exception as e:
        print("There's a problem with this article:", metadata)  # todo: better error logging
        raise e

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
    article_div: BeautifulSoup
    for article_div in soup.findAll('div', {'class': 'article-content'}):
        a_title = article_div.find('a', {'class': 'title-link'})
        try:
            parsed = parse_article(BASE_URL + a_title.get('href'))
        except Exception as e:
            print("\t", e.args[0])
            continue

        scraped_articles.append(parsed)
        if dump_dir is not None:
            print("| Trying to save to to file.", end=" | ")
            filename = f"{os.path.join(dump_dir, parsed['doi'].split('/')[-1])}.json"
            if os.path.exists(filename):
                print("Warning! File already exists. Will overwrite.", end=" | ")
            with open(filename, 'w+', encoding="utf-8") as fp:
                json.dump(parsed, fp, ensure_ascii=False)
            print(f"Saved metadata to {filename}. | ")

    return scraped_articles


def crawl(dump_dir=None):
    """
    Crawls through the MDPI database.

    :param dump_dir:
    :type dump_dir:
    :return: a list of dicts containing metadata of found articles.
    :rtype: list
    """

    if dump_dir is not None:
        if not os.path.exists(dump_dir):
            os.mkdir(dump_dir)

    soup = _cook(BASE_SEARCH_URL)

    pages_count = learn_search_pages(soup)

    scraped_articles = []

    # for i in range(int(0, pages_count)):
    for i in range(2):  # change this line to the one above to crawl through everything
        scraped_articles += page_crawl(f"{BASE_SEARCH_URL}&page_no={i + 1}", dump_dir=dump_dir)
        print(f"{i + 1} search pages crawled.", end=" ")
        print(f"{len(os.listdir(dump_dir))} files in dump_dir.")

    print("Done crawling through MDPI.")
    print("Total number of scraped articles: ", len(scraped_articles))

    return scraped_articles


if __name__ == '__main__':
    scraped = crawl(dump_dir="scraped/mdpi/articles")

    # with open("scraped_mdpi_articles_metadata.json", 'w+', encoding="utf-8") as fp:
    #     json.dump(scraped, fp)

    print(f"Number of reviewed articles found: {len([a for a in scraped if a['has_reviews']])}")
