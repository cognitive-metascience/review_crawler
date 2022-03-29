import os
import pytest

from .. import mdpi_crawler

dumpdir = os.path.join(os.path.dirname(__file__), 'dumps')

# def test_page_crawl():
#     result = mdpi_crawler.page_crawl("https://www.mdpi.com/search?journal=oceans&article_type=research-article")
#     for r in result:
#         print(r)

def test_parse_article():
    result = mdpi_crawler.parse_article("https://www.mdpi.com/2673-4087/2/3/21", dump_dir=dumpdir)
    assert len(result) > 0