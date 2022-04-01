import os
import pytest

from .. import plos_crawler

dumpdir = os.path.join(os.path.dirname(__file__), 'dumps')

# TODO: logs are currently saved to the base folder (/review_crawler/logs),
#        could be saved instead to /review_crawler/tests/logs

# def test_page_crawl():
#     result = plos_crawler.page_crawl("
#     for r in result:
#         print(r)

def test_get_metadata_from_url():
    result = plos_crawler.get_metadata_from_url("https://journals.plos.org/plosone/article/peerReview?id=10.1371/journal.pone.0262049", dump_dir=dumpdir)
    assert len(result) > 0