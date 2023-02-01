import os
import json

class ReviewCrawler:

    def parse_corpus(self):
        raise NotImplementedError
    
    def parse_article_xml(self):
        raise NotImplementedError
    
    def parse_subarticle(self):
        raise NotImplementedError
    
    def get_article_files(self):
        raise NotImplementedError