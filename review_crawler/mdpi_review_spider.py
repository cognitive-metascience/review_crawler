import json
import re
from bs4 import BeautifulSoup
import requests
import scrapy
import os

# patterns
HARD_SPACE_REGEX = re.compile(r'\xa0')  # cleans up no-break spaces
REPEATING_REVIEWS= "This manuscript is a resubmission of an earlier submission. The following is a list of the peer review reports and author responses from that submission."
NUMBERS_PATTERN = re.compile(r"\d+")
ROUND_NUMBER_PATTERN = re.compile(r"^Round(\s|(&nbsp;))+\d+$")
REVIEWER_REPORT_PATTERN = re.compile(r"^Reviewer(\s|(&nbsp;))+\d+ Report$")
AUTHOR_RESPONSE_PATTERN = re.compile(r"^Author(\s|(&nbsp;))+Response$")
DOI_PATTERN = re.compile(r"https://doi\.org/10.\d{4,9}/[-._;()/:a-zA-Z0-9]+")  # from https://www.crossref.org/blog/dois-and-matching-regular-expressions/

class MdpiReviewSpider(scrapy.Spider):
    name="mdpi_review"
    allowed_domains = ['www.mdpi.com', 'susy.mdpi.com']
    shorten_doi = lambda s, doi: doi.split('/')[-1]

    def __init__(self, url=None, dump_dir=None, update=False, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.handle_httpstatus_list = [404]
        self.dump_dir = dump_dir
        self.files_dumped_counter = 0
        if not update:
            self.update = update
        else:
            self.update = update.lower() in ("yes", "true", "t", "1")
        if url is None:
            if dump_dir is None:
                e = "Cannot scrape a review without providing one of: dump_dir or url."
                self.logger.error(e)
            else:
                self.start_urls = self.find_urls()
        else:
            self.start_urls = [url]
        self.logger.info("Setting up a MdpiReviewSpider: "+
         f"len(start_urls)={len(self.start_urls)}, dump_dir={self.dump_dir}, update={self.update}")

            
    def find_urls(self):
        """finds urls containing reviews from article metadata in dump_dir"""
        urls = []
        for dir in os.listdir(self.dump_dir):
            # dump_dir should contain directories named after dois
            # with files named metadata.json
            if os.path.isfile(dir): 
                continue
            if not os.path.exists(os.path.join(self.dump_dir, dir, 'metadata.json')):
                self.logger.warning(f"Unexpectedly, didn't find file with metadata in dump_dir/{dir}")
                continue
            with open(os.path.join(self.dump_dir, dir, 'metadata.json'), 'r') as fp:
                try:
                    meta = json.load(fp)
                    if meta['has_reviews']:
                        urls.append(meta['reviews_url']) 
                except json.JSONDecodeError:
                    self.logger.error("JSONDecodeError while reading metadata from "+dir)
        self.logger.info(f'Found {len(urls)} urls in dump_dir with reviews to scrape.')
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

    def parse_reviews(self, response):
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        
        if self.dump_dir is not None:
            sub_a_dir =  a_short_doi + '/sub-articles'
            os.makedirs(os.path.join(self.dump_dir, sub_a_dir), exist_ok=True)
        
        # find reviewers' names
        reviewers = {}
        for div in response.css('div[style="display: block;font-size:14px; line-height:30px;"]'):
            texts = [x.get().strip() for x in div.css('::text')]
            r_no = int(re.search(NUMBERS_PATTERN, texts[0]).group())
            reviewers[r_no] = {'number': r_no, 'name': texts[1].strip()}
        
        i = 0
        rev_no = 0
        ard = {}
        dump  = False
        clean_prev_ard = False

        # find the div with article content and iterate over it
        absdiv = response.xpath('.//div[@class="abstract_div"]/div[not(@*)]')
        for p in absdiv.xpath('./p | .//li'):
            soup = BeautifulSoup(p.get(), 'lxml')
            text = HARD_SPACE_REGEX.sub(' ', soup.get_text().strip())
            if REPEATING_REVIEWS in text:
                break
            # look for a "Round #" heading 
            if ROUND_NUMBER_PATTERN.match(text):
                round_no = int(NUMBERS_PATTERN.search(text).group())
                i=1
                continue

            # look for the start of a review
            elif REVIEWER_REPORT_PATTERN.match(text):
                if len(ard) > 0:
                    clean_prev_ard = True
                    prev_ard = ard
                if dump:
                    fp.close()
                    self.files_dumped_counter += 1
                rev_no = int(NUMBERS_PATTERN.search(text).group())
                ard = {
                        'url': response.url,
                        'id' : f"{a_short_doi}.r{round_no}{rev_no}",
                        'original_article_doi': original_a_doi,
                        'original_article_url': response.url[:response.url.rfind('review')],
                        'type': "review",
                        'reviewer': reviewers[rev_no],
                        'round': round_no,
                        'supplementary_materials': []
                    }
                if self.dump_dir is not None:
                    filen = ard['id']
                    filename = filen +'.txt'
                    ard['supplementary_materials'].append(
                        {'filename':filename,  'id':filen, 
                        'title':"This sub_article in plaintext."})
                    # open a file for writing plaintext article content
                    fp = open(os.path.join(self.dump_dir, sub_a_dir, filename), 'w+')
                    dump = True
                
            # look for the start of an author response
            elif AUTHOR_RESPONSE_PATTERN.match(text):
                if len(ard) > 0:
                    clean_prev_ard = True
                    prev_ard = ard
                    if dump:
                        fp.close()
                        self.files_dumped_counter += 1
                ard = {
                    'url': response.url,
                    'id' : f"{a_short_doi}.a{round_no}{rev_no}",
                    'original_article_doi': original_a_doi,
                    'original_article_url': response.url[:response.url.rfind('review')],
                    'type': "author-comment",
                    'round': round_no,
                    'replying_to': rev_no,
                    'supplementary_materials': []
                }
                if self.dump_dir is not None:
                    filen = ard['id']
                    filename = filen +'.txt'
                    ard['supplementary_materials'].append(
                        {'filename':filename,  'id':filen, 
                        'title':"This sub_article in plaintext."})
                    # open a file for writing plaintext article content
                    fp = open(os.path.join(self.dump_dir, sub_a_dir, filename), 'w+')
                    dump = True
            
            # look for links to supplementary materials
            for a in p.xpath('.//a'):
                file_url = a.css('::attr(href)').get()
                orig_filename = a.css('::text').get().strip()
                filex = os.path.splitext(orig_filename)[1]
                # arbitrary generaion of id's
                sm_id = f"{a_short_doi}.s{ard['round']}{i}"
                i+=1
                try:
                    sm_type = file_url.split('=')[1][:file_url.split('=')[1].rfind('&')]
                except:
                    sm_type = 'NA'
                sm = {
                    'id': sm_id, 'filename': sm_id+filex, 'type' :sm_type,
                    'original_filename': orig_filename, 'url': file_url,
                    'title': os.path.splitext(orig_filename)[0] 
                }
                ard['supplementary_materials'].append(sm)
                # download this supplementary material:
                if self.dump_dir is not None:
                    sm_path = os.path.join(self.dump_dir, sub_a_dir, sm['filename'])
                    if os.path.exists(sm_path) and not self.update:
                        self.logger.info(f"{sm['filename']} already exists. Will NOT overwrite.")
                    else:
                        with open(sm_path, 'wb') as f:
                            self.logger.debug(f"Downloading supplementary material from {sm['url']}")
                            r = requests.get(sm['url'], stream=True)
                            f.write(r.content)
                            self.files_dumped_counter += 1
            if clean_prev_ard:
                yield prev_ard
                if dump:
                    self.dump_metadata(prev_ard, sub_a_dir, prev_ard['id'])
                clean_prev_ard = False
            if dump:
                fp.write(text+'\n')
        yield ard
        if dump:
            self.dump_metadata(ard, sub_a_dir, ard['id'])
    
        if self.dump_dir is not None:
            self.logger.info(f"Dumped {self.files_dumped_counter} files so far.")
                    


    def parse_embedded_reviews(self, response):
        """Parses reviews embedd in the original article url. The provided url might end in `#review_report`.
        """        
        div = response.css('div.bib-identity')
        original_a_doi = DOI_PATTERN.search(div.get()).group()
        a_short_doi = self.shorten_doi(original_a_doi)
        ard_id = a_short_doi+'.r1'

        if self.dump_dir is not None:
            sub_a_dir =  a_short_doi + '/sub-articles'
            os.makedirs(os.path.join(self.dump_dir, sub_a_dir), exist_ok=True)
        ard = {
                'url': response.url + '#review_report',
                'id': ard_id,
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
                        self.logger.info(f"{filename} already exists. Will NOT overwrite.")
                    else:
                        with open(sm_path, 'wb') as fp:
                            self.logger.debug(f'Downloading supplementary material from {url}')
                            r = requests.get(url, stream=True)
                            fp.write(r.content)
                            self.files_dumped_counter += 1
        if self.dump_dir is not None:
            self.dump_metadata(ard, sub_a_dir, ard_id)    # todo: change the naming convention?
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
        self.logger.debug(f"Saving metadata to file in {'/'.join(dirpath.split('/')[:-5])}.")
        try:
            filepath = f"{os.path.join(dirpath, filename)}.json"
            if os.path.exists(filepath) and not self.update:
                self.logger.info(f"metadata already exists in {dirname}. Will NOT overwrite.")
            else:
                if os.path.exists(filepath):
                    self.logger.info(f"metadata already exists in {dirname}. Will overwrite!")
                with open(filepath, 'w+', encoding="utf-8") as fp:
                    json.dump(metadata, fp, ensure_ascii=False)

            
        except Exception as e:
            self.logger.exception(f"Problem while saving to file: {dirname}/{filename}\n{e}")
        else:
            self.logger.info(f"Saved metadata to {dirname}/{filename}.json")
            self.files_dumped_counter += 1

