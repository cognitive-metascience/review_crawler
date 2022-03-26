
import json
import os
import shutil
import requests
from bs4 import BeautifulSoup
from typing import Union


def _cook(url: str) -> Union[BeautifulSoup, None]:
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup

def filter_articles(src, dest):
    for file in os.listdir(os.path.abspath(src)):
        filepath = os.path.join(os.path.abspath(src),file)
        with open(filepath) as fp:
            article = json.load(fp)
            for key in article.keys():
                print(f"{key}: {article[key]}")
            if article["has_reviews"]:
                shutil.move(filepath, dest)

if __name__ == "__main__":
    # articles_dir = "./mdpi/scraped/articles"
    # output_dir = "./mdpi/scraped/filtered"
    filter_articles(articles_dir, output_dir)