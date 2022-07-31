import pytest
import os
import random

from .. import elife_crawler

sample_filename = 'elife-47612-v2.xml'

corpus_path = elife_crawler.elife_corpus_path

NUM_RANDOM_ARTICLES = 100

@pytest.fixture
def sample_article():
    return open(os.path.join(corpus_path, sample_filename), 'rb').read()
    
@pytest.fixture
def random_articles():
    files = os.listdir(corpus_path)
    articles = []
    for i in range(NUM_RANDOM_ARTICLES):
        filename = random.choice(files)
        articles.append(open(os.path.join(corpus_path, filename), 'rb').read())
    return articles


def test_get_article_files():
    seen_articles = set()
    for filename, fp in elife_crawler.get_article_files():
        filen = os.path.splitext(filename)
        assert filen[1].lower() == '.xml'
        splat = filen[0].split('-v')
        assert splat[0] not in seen_articles
        seen_articles.add(splat[0])
        
def test_parse_article_xml(sample_article):
    res = elife_crawler.parse_article_xml(sample_article)
    assert 'doi' in res
    assert res['has_reviews']
    for sub_a in res['sub_articles']:
        assert sub_a['original_article_doi'] == res['doi']
    
def test_random_articles(random_articles):
    for article in random_articles:
        res = elife_crawler.parse_article_xml(article)
        assert 'doi' in res
        assert len(res['authors']) > 0