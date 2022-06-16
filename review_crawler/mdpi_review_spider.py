import json
import re
from bs4 import BeautifulSoup
import requests
import scrapy
import os

# patterns
REPEATING_REVIEWS= "This manuscript is a resubmission of an earlier submission. The following is a list of the peer review reports and author responses from that submission."
NUMBERS_PATTERN = re.compile(r"\d+")
ROUND_NUMBER_PATTERN = re.compile(r"Round \d+")
REVIEWER_REPPORT_PATTERN = re.compile(r"Reviewer \d+ Report")
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/

class MdpiReviewSpider(scrapy.Spider):
    name="mdpi_review"
    allowed_domains = ['www.mdpi.com']
    shorten_doi = lambda self, doi: doi.split('/')[-1]

    def __init__(self, url=None, dump_dir=None, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.handle_httpstatus_list = [404]
        self.logger.info(f"Setting up a MdpiReviewSpider. url={url}, dump_dir={dump_dir}")
        self.dump_dir = dump_dir
        if dump_dir is None:
            self.start_urls=[url]
            if url is None:
                e = "Cannot scrape a review without providing one of: dump_dir or url."
                self.logger.error(e)
        else:
            # find urls containing reviews from article metadata in dump_dir
            self.start_urls = []
            for dir in os.listdir(self.dump_dir):
                # dump_dir should contain directories named after dois
                # with files named metadata.json
                if os.path.isfile(dir): 
                    continue
                if not os.path.exists(os.path.join(self.dump_dir, dir, 'metadata.json')):
                     continue
                if os.path.exists(os.path.join(self.dump_dir, dir, 'sub-articles')):
                    pass
                    # continue    # comment this line to overwrite existing files
                
                with open(os.path.join(self.dump_dir, dir, 'metadata.json'), 'r') as fp:
                    meta = json.load(fp)
                    if meta['has_reviews']:
                        self.start_urls.append(meta['reviews_url']) 

    def parse(self, response):
        if response.status == 404:
            # ugly fix:
            # response.url should end with '#review_report', not '/review_report'
            newurl = response.url[::-1].replace('/','#',1)[::-1]
            yield response.follow(newurl, callback = self.parse_embedded_reviews)
        else:
            return self.parse_reviews(response)

    
    def parse_reviews(self, response):
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        
        if self.dump_dir is not None:
            sub_a_dir =  a_short_doi + '/sub-articles'
            os.makedirs(os.path.join(self.dump_dir, sub_a_dir), exist_ok=True)
        
        reviewers = []
        for div in response.css('div[style="display: block;font-size:14px; line-height:30px;"]'):
            texts = [x.get().strip() for x in div.css('::text')]
            reviewers.append({
                'number': re.search(NUMBERS_PATTERN, texts[0]).group(),
                'name': texts[1].strip()})

        ard = {}
        flag = True
        dump  = False
        for p in response.css('div.abstract_div p,ul'):
            if not flag: break
            soup = BeautifulSoup(p.get(), 'lxml')
            text = soup.get_text().strip()
            if REPEATING_REVIEWS in text:
                break
            # TODO: find links to files with additional documents
            for span in p.css('span[style="font-size: 18px; margin-top:10px;"]'):
                if ROUND_NUMBER_PATTERN.match(span.css('::text').get()):
                    round_no = NUMBERS_PATTERN.search(span.css('::text').get()).group()
                    ard = {
                            'url': response.url,
                            'original_article_doi': original_a_doi,
                            'original_article_url': response.url[:response.url.rfind('review')],
                            'type': "aggregated-review-documents",
                            'reviewers': reviewers,
                            'round': round_no,
                            'supplementary_materials': []
                        }

                    if self.dump_dir is not None:
                        filen = a_short_doi+'.r'+round_no
                        filename = filen +'.txt'
                        ard['supplementary_materials'].append(
                            {'filename':filename,'title':"This sub_article in plaintext."})
                        self.dump_metadata(ard, sub_a_dir, filen)
                        if dump:
                            fp.close()
                        fp = open(os.path.join(self.dump_dir, sub_a_dir, filename), 'w+')
                        dump = True
                    yield ard
            if dump:
                fp.write(text+'\n')
                    

    def parse_embedded_reviews(self, response):
        """Parses reviews embedd in the original article url. The provided url might end in `#review_report`.
        """        
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        if self.dump_dir is not None:
            sub_a_dir =  a_short_doi + '/sub-articles'
            os.makedirs(os.path.join(self.dump_dir, sub_a_dir), exist_ok=True)
        ard = {
                'url': response.url + '#review_report',
                'original_article_doi': original_a_doi,
                'original_article_url': response.url,
                'type': "aggregated-review-documents",
                'supplementary_materials': []
                }
        xp = response.css('ul[style="margin:0; list-style: none; overflow: auto;"] li')
        for x in xp:
            a, b = x.css('a[href]'), x.css('b::text')
            if "review report" in b.get().lower():
                p = x.css('p::text')
                url = 'https://www.mdpi.com'+ a.css('::attr(href)').extract()[0]
                filex = p.extract()[1].split(',')[0].strip()[1:].lower()
                orig_filename = b.get()[:-1] +'.'+ filex
                id = f"{a_short_doi}.{url[url.rfind('/')+1:url.find('?')]}"
                filename = f"{id}.{filex}"
                with open(os.path.join(self.dump_dir, sub_a_dir, filename), 'wb') as fp:
                    self.logger.debug(f'Downloading supplementary material from {url}')
                    r = requests.get(url, stream=True)
                    fp.write(r.content)
                
                ard['supplementary_materials'].append({
                        'filename':filename, 'id': id, 
                        'original_filename': orig_filename, 
                        'title':b.get()[:-1]})
        yield ard
                



    def dump_metadata(self, metadata, dirname=None, filename='metadata'):
        """Takes a dictionary containing article metadata and saves it to a JSON file in `self.dump_dir`.

        Args:
            metadata (dict): dictionary to be saved to file.
            dirname (str, optional): If specified, a directory inside `self.dump_dir` will be created (if it doesn't exist) and the metadata is saved there. Defaults to None.
            filename (str, optional): Base file name (without an extension). Defaults to 'metadata'.
        """
        assert self.dump_dir is not None
        if dirname is None:
            dirpath = self.dump_dir
        else:
            dirpath = os.path.join(os.path.abspath(self.dump_dir), dirname)
        os.makedirs(dirpath, exist_ok=True)
        self.logger.debug(f"Saving metadata to file in {dirpath}.")
        try:
            filepath = f"{os.path.join(dirpath, filename)}.json"
            if os.path.exists(filepath):
                self.logger.warning(f"metadata already exists in {dirname}. Will overwrite.")
            with open(filepath, 'w+', encoding="utf-8") as fp:
                json.dump(metadata, fp, ensure_ascii=False)
        except Exception as e:
            self.logger.exception(f"Problem while saving to file: {dirname}/{filename}\n{e}")
        else:
            self.logger.info(f"Saved metadata to {dirname}/{filename}.json")

