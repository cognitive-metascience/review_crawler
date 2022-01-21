# simple test script for crawling through retractions of MDPI articles
# only the first page of the search (max 200 retractions)
# prints out the title and doi of the original articles and nothing more

import requests
# import lxml
import re
from bs4 import BeautifulSoup

doi_pattern = re.compile(r"doi\.org/")

search_url = "https://www.mdpi.com/search?page_count=200&article_type=retraction"
r = requests.get(search_url)

soup = BeautifulSoup(r.content, 'lxml')
found_articles = []
article: BeautifulSoup
for article in soup.findAll('div', {'class': 'article-content'}):
    temp_dict = {'title': article.find('a', {'class': 'title-link'}).getText(strip = True,),
                 'doi': article.find('a', {'href': doi_pattern}).get('href')}
    found_articles.append(temp_dict)

for item in found_articles:
    print(item) # todo: save to file instead