import re
import scrapy

from review_crawler.article_spider import ArticlesSpider

SEARCH_PAGES_PATTERN = re.compile(r"of ([\d,]+)")
CHECKS = lambda a: "Correction:" not in a.get()

class ELifeSpider(ArticlesSpider):

    name = "elife"
    allowed_domains = ["elifesciences.org"]
    base_url = "https://elifesciences.org"
    base_search_url = base_url + "/search?for=&types[0]=research&sort=date&order=descending&page="
    
    
    def __init__(self, dump_dir=None, start_page=None, stop_page=None, name=None, **kwargs):
        super().__init__(dump_dir, start_page, stop_page, name, **kwargs)
        
        
    def parse_searchpage(self, response):
        articles = filter(self.CHECKS, response.css('a.teaser__header_text_link'))
        
    def learn_search_pages(self, response):
        t = response.xpath('/html/body/div[1]/div/main/header/div').css('::text').extract_first()
        hit = SEARCH_PAGES_PATTERN.search(t)
        if hit is not None:
            res = int(hit.groups()[0].replace(',',''))
            self.log(f"It seems there are {res} search pages for this query.")
            return res
        else:
            return None
        
    
    