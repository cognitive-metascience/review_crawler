import os
import pytest
import plos_crawler

dumpdir = os.path.join(os.path.dirname(__file__), 'dumps')

# def test_page_crawl():
#     result = plos_crawler.page_crawl("
#     for r in result:
#         print(r)

def test_parse_article():
    result = plos_crawler.parse_article("https://journals.plos.org/plosone/article/peerReview?id=10.1371/journal.pone.0262049", dump_dir=dumpdir)
    assert len(result) > 0