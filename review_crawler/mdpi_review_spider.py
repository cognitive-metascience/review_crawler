import json
import re
from bs4 import BeautifulSoup
import scrapy
import os

# patterns
REPEATING_REVIEWS= "This manuscript is a resubmission of an earlier submission. The following is a list of the peer review reports and author responses from that submission."
NUMBERS_PATTERN = re.compile(r"\d+")
ROUND_NUMBER_PATTERN = re.compile(r"Round \d+")
REVIEWER_REPPORT_PATTERN = re.compile(r"Reviewer \d+ Report")

class MdpiReviewSpider(scrapy.Spider):
    name="mdpi_review"
    allowed_domains = ['www.mdpi.com']
    shorten_doi = lambda self, doi: doi.split('/')[-1]

    def __init__(self, url=None, dump_dir=None, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.logger.info(f"Setting up a MdpiSpider. url={url}, dump_dir={dump_dir}")
        if dump_dir is None:
            self.start_urls=[url]
        self.dump_dir = dump_dir
        if dump_dir is None and url is None:
            e = "Cannot scrape a review without providing one of: dump_dir or url."
            self.logger.error(e)

    def start_requests(self):
        assert self.dump_dir is not None
        # dump_dir should contain directories named after dois
        # with files named metadata.json
        for dir in os.listdir(self.dump_dir):
            if not os.path.isdir(dir): continue
            with open(os.path.join(self.dump_dir, dir, 'metadata.json'), 'r') as fp:
                meta = json.load(fp)
                if meta['has_reviews']:
                    yield meta['reviews_url']

    
    def parse_reviews(self, response):
        
        a_short_doi = self.shorten_doi(response.css('div.bib-identity a::text').get())
        if self.dump_dir is not None:
            sub_a_dir = os.path.join(self.dump_dir, a_short_doi, 'sub-articles')
            os.makedirs(sub_a_dir)
            filen=os.path.join(sub_a_dir, a_short_doi)  # file extension to be concatenated later
        reviewers = []
        for div in response.css('div[style="display: block;font-size:14px; line-height:30px;"]'):
            texts = [x.get().strip() for x in div.css('::text')]
            reviewers.append({
                'number': re.search(NUMBERS_PATTERN, texts[0]).group(),
                'name': texts[1].strip()})

        all_metadata = []
        
        ard = {}
        flag = True
        dump  = False
        for p in response.css('div.abstract_div p,ul'):
            if not flag: break
            soup = BeautifulSoup(p.get())
            text = soup.get_text().strip()
            if REPEATING_REVIEWS in text:
                self.logger.warning(
                    f'Reviews may be duplicated for {a_short_doi}, REPEATING_REVIEWS pattern found in html. Default behavior is to save the whole thing as-is.')
                # uncomment the line below to try to stop the loop earlier and avoid repeats
                # break
            for span in p.css('span[style="font-size: 18px; margin-top:10px;"]'):
                if ROUND_NUMBER_PATTERN.match(span.css('::text').get()):
                    round_no = NUMBERS_PATTERN.search(span.css('::text').get()).group()
                    ard = {
                            'url': response.url,
                            'original_article_doi': response.css('div.bib-identity a::text').get(),
                            'type': "aggregated-review-documents",
                            'reviewers': reviewers,
                            'round': round_no
                        }
                    if self.dump_dir is not None:
                        filename = filen+'0'*(3-len(round_no))+'r'+round_no+'.txt'
                        ard['supplementary_materials'] = [{'original_filename':filename}]
                        self.dump_metadata(ard, sub_a_dir, filen+'.json')
                        if dump:
                            fp.close()
                        fp = open(filename, 'x')
                        dump = True
                    yield ard
            if dump:
                fp.write(text)
                    
