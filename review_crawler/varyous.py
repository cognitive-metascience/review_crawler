
import requests
from bs4 import BeautifulSoup
from typing import Union


def _cook(url: str) -> Union[BeautifulSoup, None]:
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup

