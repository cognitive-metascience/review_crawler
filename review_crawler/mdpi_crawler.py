"""
test crawler for the MDPI database.
goes through first 10 pages of search results = 100 articles
currently scrapes the title and doi only, dumps data into a json file
todo: perhaps save data to file as we crawl, instead of creating a gigantic list of articles
"""

# import lxml
import json
import re

import requests
from bs4 import BeautifulSoup

BASE_SEARCH_URL = 'https://www.mdpi.com/search?page_count=10&article_type=research-article&view=compact'

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
    return int(re.findall(r"\d+", hit)[-1])


def page_crawl(page_no):
    """
    Crawls through a single page of search results.

    :param page_no: Page number to crawl through.
    :type page_no: int
    :return: A list of dicts containing metadata of found articles.
    :rtype: list
    """
    current_page_url = BASE_SEARCH_URL + "&page_no=" + str(page_no)
    soup = BeautifulSoup(requests.get(current_page_url).content, 'lxml')

    articles = []

    article: BeautifulSoup
    for article in soup.findAll('div', {'class': 'article-content'}):
        temp_dict = {}
        try:
            temp_dict['title'] = article.find('a', {'class': 'title-link'}).getText(strip=True)

            print(f"P#{page_no} | Currently scraping: {temp_dict['title']}")

            temp_dict['doi'] = DOI_PATTERN.search(article.getText()).group()

            if "(registering" in article.getText():     # problematic moment
                #     temp_dict['doi'] = DOI_PATTERN.search(article.getText).group()
                temp_dict['doi_registered'] = False
            else:
                #     temp_dict['doi'] = article.find('a', {'href': DOI_PATTERN}).get('href')
                temp_dict['doi_registered'] = True
            articles.append(temp_dict)
        except Exception as e:
            print("There's a problem with this article: ", temp_dict['title'])
            raise e
    return articles


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
    for i in range(10):    # change this to the above line to crawl through everything
        scraped_articles += page_crawl(i+1)

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
