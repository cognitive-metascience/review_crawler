import json
import re
import pandas as pd
from bs4 import BeautifulSoup
import requests
import os

from crawling.spiders.article_spider import ArticlesSpider
from scrapy.exceptions import CloseSpider

# patterns
HARD_SPACE_REGEX = re.compile(r'\xa0')  # cleans up no-break spaces
REPEATING_REVIEWS = "This manuscript is a resubmission of an earlier submission. The following is a list of the peer review reports and author responses from that submission."
NUMBERS_PATTERN = re.compile(r"\d+")
ROUND_NUMBER_PATTERN = re.compile(r"Round \d+")
REVIEWER_REPPORT_PATTERN = re.compile(r"Reviewer \d+ Report")
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/


class MdpiReviewSpider(ArticlesSpider):
    handle_httpstatus_list = [404]
    name="mdpi_review"
    allowed_domains = ['www.mdpi.com', 'susy.mdpi.com']
    shorten_doi = lambda self, doi: doi.split('/')[-1]

    def __init__(self, url=None, dump_dir=None, update='no', save_html='no', skip_sm_dl='yes', name=None, **kwargs):
        super().__init__(dump_dir=dump_dir, update=update, save_html=save_html, name=name, **kwargs)
        if url is None:
            if self.dump_dir is None:
                e = "Cannot scrape a review without providing one of: `dump_dir` or `url`."
                self.logger.critical(e)
                raise CloseSpider()
            else:
                self.start_urls = self.find_urls()
        else:
            self.start_urls = [url]
        self.skip_sm_dl = skip_sm_dl.lower() not in ("no", "n", "false", "f", "0")
        self.logger.info(f"[mdpi review spider] len(start_urls)={len(self.start_urls)}, dump_dir={self.dump_dir}, update={self.update}, skip_sm_dl={self.skip_sm_dl}")

            
    def find_urls(self):
        """finds urls containing reviews from article metadata in dump_dir"""
        urls = []
        self.logger.debug("Attempting to find_urls for mdpi reviews...")
        
        # load a file with corpus metadata with urls of reviews
        if os.path.exists(os.path.join(self.dump_dir, "reviews-urls.csv")):  #  (for now filename is harcoded, possibly could be a spider argument)
            self.logger.debug("Located reviews-urls.csv in dump_dir!")
            df = pd.read_csv(os.path.join(self.dump_dir, "reviews-urls.csv"))
            if len(df) == 0:
                self.logger.debug("But there are no urls to be found...")
            else:
                if 'skip' in df:
                    df = df[~df.skip]  # filter urls that should be skipped
                urls = df.reviews_url.to_list()
            
        if len(urls) == 0:
            self.logger.debug("Going through dump_dir to find urls of reviewed articles...")
            df = pd.DataFrame()
            for i, dir in enumerate(os.listdir(self.dump_dir)):
                # dump_dir should contain directories named after dois with files named metadata.json
                if os.path.isfile(dir): 
                    continue
                if not os.path.exists(os.path.join(self.dump_dir, dir, 'metadata.json')):
                    self.logger.warning(f"Unexpectedly, didn't find file with metadata in dump_dir/{dir}")
                    continue
                if not self.update and os.path.exists(os.path.join(self.dump_dir, dir, 'sub-articles')):
                    if len(os.listdir(os.path.join(self.dump_dir, dir, 'sub-articles'))) > 0:
                        self.logger.debug(f"Skipping doi {dir} as it already has a sub-articles folder.")
                        continue
                with open(os.path.join(self.dump_dir, dir, 'metadata.json'), 'r', encoding="utf-8") as fp:
                    meta = json.load(fp)
                    if meta['has_reviews']:
                        df = pd.concat([df, pd.DataFrame({
                            'doi': meta['doi'],
                            'reviews_url': meta['reviews_url']
                                }, index=[i])])
                        urls.append(meta['reviews_url']) 
                if (i-1)%1000 == 0:
                    self.logger.debug(f"{len(urls)} urls with reviews found thus far.")
            df.to_csv(os.path.join(self.dump_dir, "reviews-urls.csv"), index = False)
        return urls


    def parse(self, response):
        if response.status == 404:
            # ugly fix:
            # response.url should end with '#review_report', not '/review_report' <- this is an issue with mdpispider
            newurl = response.url[::-1].replace('/','#',1)[::-1]
            self.log('Parsing reviews embedded in article page.')
            yield response.follow(newurl, callback = self.parse_embedded_reviews)
        elif response.url.endswith('#review_report') or not response.url.endswith('review_report'):
            self.log('Parsing reviews embedded in article page.')
            yield from self.parse_embedded_reviews(response)
        elif response.url.endswith('review_report'):
            self.log('Parsing reviews from subpage: /review_report')
            yield from self.parse_reviews(response)

    # Remember: D6

    def parse_reviews(self, response):
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        
        if self.dump_dir is not None:
            self.dump_html(response, a_short_doi, a_short_doi)
            sub_a_dir =  os.path.join(a_short_doi, 'sub-articles')
            os.makedirs(os.path.join(self.dump_dir, sub_a_dir), exist_ok=True)
        
        reviewers = []
        for div in response.css('div[style="display: block;font-size:14px; line-height:30px;"]'):
            texts = [x.get().strip() for x in div.css('::text')]
            reviewers.append({
                'number': re.search(NUMBERS_PATTERN, texts[0]).group(),
                'name': texts[1].strip()})
        ard = {}
        dump  = False
        for p in response.css('div.abstract_div p, ul, ol'):
            soup = BeautifulSoup(p.get(), 'lxml')
            text = soup.get_text().strip()
            if REPEATING_REVIEWS in text:
                break
            for span in p.css('span[style="font-size: 18px; margin-top:10px;"]'):
                span_text = HARD_SPACE_REGEX.sub('', span.css('::text').get())  #
                i = 1
                if ROUND_NUMBER_PATTERN.match(span_text):
                    round_no = NUMBERS_PATTERN.search(span_text).group()
                    ard = {
                            'url': response.url,
                            'original_article_doi': original_a_doi,
                            'original_article_url': response.url[:response.url.rfind('review')],
                            'type': "aggregated-review-documents",
                            'reviewers': reviewers,
                            'round': round_no,
                            'supplementary_materials': []
                        }
                    for a in response.css('div#abstract.abstract_div div p a'):   ### PROBABLY PROBLEMATIC - TODO DON'T DO THE CSS ON RESPONSE, DO IT ON span or p INSTEAD!!!
                        file_url = a.css('::attr(href)').get()
                        if file_url.startswith('/'):
                            # most likely a missing http schema...
                            file_url = "https:/" + file_url
                        orig_filename = a.css('::text').get().strip()
                        filex = os.path.splitext(orig_filename)[1]
                        # arbitrary generaion of id's
                        sm_id = a_short_doi+'.s'+str(i)
                        i+=1
                        try:
                            sm_type = file_url.split('=')[1][:file_url.split('=')[1].rfind('&')]
                        except:
                            sm_type = 'NA'
                        ard['supplementary_materials'].append({
                            'id': sm_id, 'filename': sm_id+filex, 'type' :sm_type,
                            'original_filename': orig_filename, 'url': file_url,
                            'title': os.path.splitext(orig_filename)[0] 
                        })

                    if self.dump_dir is not None:
                        if not self.skip_sm_dl:
                            # download supplementary materials:
                            for sm in ard['supplementary_materials']:
                                sm_path = os.path.join(self.dump_dir, sub_a_dir, sm['filename'])
                                if os.path.exists(sm_path) and not self.update:
                                    self.logger.debug(f"{sm['filename']} already exists. Will NOT overwrite.")
                                elif "email-protection" in sm['url']:
                                    self.logger.error(f"Impossible to download {sm['filename']} from {sm['url']} due to {sm['original_filename']}")
                                else:
                                    with open(sm_path, 'wb') as f:
                                        self.logger.debug(f"Downloading supplementary material from {sm['url']}")
                                        r = requests.get(sm['url'], stream=True)
                                        f.write(r.content)
                                        self.files_dumped_counter += 1
                        # save plaintext to files
                        filen = a_short_doi+'.r'+round_no
                        filename = filen +'.txt'
                        ard['supplementary_materials'].append(
                            {'filename':filename,  'id':filen, 
                            'title':"This sub_article in plaintext."})
                        self.dump_metadata(ard, sub_a_dir, filen, overwrite = self.update)
                        if dump:
                            fp.close()
                        fp_path = os.path.join(self.dump_dir, sub_a_dir, filename)
                        if os.path.exists(fp_path) and not self.update:
                           self.logger.debug(f"{fp_path} already exists. Will NOT overwrite.") 
                        else:
                            # open a file for writing plaintext article content
                            fp = open(fp_path, 'w+', encoding="utf-8")
                            self.files_dumped_counter += 1
                            dump = True
                        
                    yield ard
            if dump:
                fp.write(text+'\n')
        
        if self.dump_dir is not None:
            self.logger.info(f"Dumped {self.files_dumped_counter} files so far.")
                    


    def parse_embedded_reviews(self, response):
        """Parses reviews embedd in the original article url. The provided url might end in `#review_report`.
            NOTE this function seems to be bugged somewhere
        """        
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        if self.dump_dir is not None:
            sub_a_dir =  os.path.join(a_short_doi, '/sub-articles')
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
                sm_id = f"{a_short_doi}.{url[url.rfind('/')+1:url.find('?')]}"
                filename = f"{sm_id}.{filex}"
                
                ard['supplementary_materials'].append({
                        'filename': filename, 'id': sm_id, 
                        'original_filename': orig_filename, 
                        'title': b.get()[:-1], 'url': url})
                if self.dump_dir is not None:
                    sm_path = os.path.join(self.dump_dir, sub_a_dir, filename)
                    if os.path.exists(sm_path) and not self.update:
                        self.logger.debug(f"{filename} already exists. Will NOT overwrite.")
                    elif not self.skip_sm_dl:
                        with open(sm_path, 'wb') as fp:
                            self.logger.debug(f'Downloading supplementary material from {url}')
                            r = requests.get(url, stream=True)
                            fp.write(r.content)
                            self.files_dumped_counter += 1
        if self.dump_dir is not None:
            self.dump_metadata(ard, sub_a_dir, a_short_doi+'.r', overwrite=self.update)    # todo: change the naming convention?
        yield ard
