"""
test crawler for the MDPI database.
goes through first 10 pages of search results = 100 articles
currently scrapes the title, url and doi only, dumps all data into a single json file
todo: save data to json files as we crawl, instead of creating a gigantic list of articles
"""

import json
import re
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.mdpi.com"
BASE_SEARCH_URL = BASE_URL + "/search?page_count=10&article_type=research-article&view=compact"

# regex patterns
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/
SEARCH_PAGES_PATTERN = re.compile(r"Displaying article \d+-\d+ on page \d+ of \d+.")


def learn_search_pages(search_soup):
    """
    Figures out how many search pages were returned after searching the MDPI database.

    :type search_soup: BeautifulSoup
    :rtype: int
    """
    hit = search_soup.find(text=SEARCH_PAGES_PATTERN)
    assert hit is not None  # will pass unless something very strange happened
    return int(re.findall(r"\d+", hit)[-1])


def page_crawl(page_no):
    """
    Crawls through a single page of MDPI search results.

    :param page_no: Page number to crawl through.
    :type page_no: int
    :return: A list of dicts containing metadata of found articles.
    :rtype: list
    """
    current_page_url = f"{BASE_SEARCH_URL}&page_no={page_no}"
    soup = BeautifulSoup(requests.get(current_page_url).content, 'lxml')

    scraped_articles = []

    # iterate over all article-content divs on the page
    article_div: BeautifulSoup
    for article_div in soup.findAll('div', {'class': 'article-content'}):
        # parse metadata from this div
        metadata = {}
        try:
            a_title = article_div.find('a', {'class': 'title-link'})
            metadata['title'] = a_title.getText(strip=True)

            print(f"P#{page_no} | Currently parsing: {metadata['title']}")

            metadata['url'] = BASE_URL + a_title.get('href')
            metadata['doi'] = re.search(DOI_PATTERN, article_div.getText()).group()

            if "(registering" in article_div.getText():  # problematic moment
                # metadata['doi'] = re.search(DOI_PATTERN, article_div.getText).group()
                metadata['doi_registered'] = False  # todo: unregistered DOI means that the article is in early access, probably better to skip those altogether
            else:
                # metadata['doi'] = article_div.find('a', {'href': DOI_PATTERN}).get('href')
                metadata['doi_registered'] = True
            scraped_articles.append(metadata)
        except Exception as e:
            print("There's a problem with this article:", metadata['title'])    # todo: better error logging
            raise e
    return scraped_articles


def crawl():
    """
    Crawls through the MDPI database.

    :return: list of dicts containing metadata of found articles.
    :rtype: list
    """
    soup = BeautifulSoup(requests.get(BASE_SEARCH_URL).content, 'lxml')
    pages_count = learn_search_pages(soup)
    scraped_articles = []

    # for i in range(int(pages_count)):
    for i in range(10):  # change this line to the one above to crawl through everything
        scraped_articles += page_crawl(i + 1)

    print("Done crawling through MDPI.")
    return scraped_articles


if __name__ == '__main__':
    scraped = crawl()
    with open('scraped_mdpi_articles_metadata.json', 'w+') as f:
        json.dump(scraped, f)

    print("Total number of scraped articles: ", len(scraped))
    registered_dois = []
    for item in scraped:
        if item['doi_registered']: registered_dois.append(item)
    print("Total number of registeed dois found: ", len(registered_dois))
