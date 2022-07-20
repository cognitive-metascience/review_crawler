"""
    Base class for inheritance for Spiders that scrape reviewed articles from paginated search results.
    `ArticlesSpider` cannot be run on its own, instead other classes should implement it.

"""

import json
import os

from scrapy import Spider

class ArticlesSpider(Spider):
    
    base_url = ""
    search_query = ""   # should end with something like `page_no=`
    
    shorten_doi = lambda self, doi: doi.split('/')[-1]
    
    def __init__(self, dump_dir=None, start_page=None, stop_page=None, name=None, **kwargs):
        super().__init__(name, **kwargs)
        self.search_url = self.base_url + self.search_query
        self.logger.info(f"Setting up a {self.name.capitalize()}Spider. start_page={start_page}, stop_page={stop_page}, dump_dir={dump_dir}")
        if dump_dir is None:
            self.logger.warning("dump_dir is None. JSON files will not be saved!")
        elif os.path.isdir(dump_dir):
            self.dump_dir = dump_dir
        else:
            self.logger.warning("Invalid dump_dir (the path provided does not exist or is not a directory). Setting dump_dir to None. JSON files will not be saved!")
            self.dump_dir = None
        if start_page is not None:
            start_url = self.search_url + str(start_page)
            self.start_page = int(start_page)
        else:
            start_url = self.search_url + "1"   # starts from page number 1 by default
            self.start_page = 1
        self.stop_page = stop_page
        self.start_urls = [start_url]
        
    def parse(self, response):
        if self.stop_page is None:
            # find out how many pages is possible to scrape
            # NOTE: you will run into errors if it's impossible to find the number of all search pages from the start_url
            stop_page = int(self.learn_search_pages(response))
        else:
            stop_page = int(self.stop_page)

        for i in range(self.start_page, stop_page):
            page = self.search_url + str(i+1)
            yield response.follow(page, callback=self.parse_searchpage)

    
    def parse_article(self, response):
        metadata = self.get_metadata_from_html(response.text)
        
        if metadata['has_reviews']:
            a_short_doi = self.shorten_doi(metadata['doi'])
            self.logger.info(f"Article {a_short_doi} probably has reviews!")
            # yield response.follow(metadata['reviews_url'], self.parse_reviews)
            metadata['sub_articles'] = []

            if self.dump_dir is not None:
               self.dump_metadata(metadata, a_short_doi)

        yield metadata  
        
    def parse_searchpage(self, response):
        raise NotImplementedError
    
    def learn_search_pages(self, response) -> int | None:
        raise NotImplementedError
    
    def get_metadata_from_html(self, html: str) -> dict:
        raise NotImplementedError
    
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
                self.logger.warning(f"metadata already exists in {dirpath}. Will overwrite.")
            with open(filepath, 'w+', encoding="utf-8") as fp:
                json.dump(metadata, fp, ensure_ascii=False)
        except Exception as e:
            self.logger.exception(f"Problem while saving to file: {filepath}.\n{e}")
        else:
            self.logger.info(f"Saved metadata to {dirname}/{filename}.json")

    