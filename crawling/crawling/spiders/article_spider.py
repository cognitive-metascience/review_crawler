"""
    Base class for inheritance for Spiders that scrape reviewed articles from paginated search results.
    `ArticlesSpider` cannot be run on its own, instead other classes should implement it.

"""

import json
import os
from bs4 import BeautifulSoup, Comment

from scrapy import Spider
from scrapy.exceptions import CloseSpider

class ArticlesSpider(Spider):
    
    base_url = ""       # provide this in inheriting sdpiders
    search_query = ""   # should end with something like `page_no=`
    
    shorten_doi = lambda self, doi: doi.split('/')[-1]
    
    def __init__(self, dump_dir=None, start_page=None, stop_page=None, update="no", save_html = 'no', name=None, **kwargs):
        # TODO add parameter no_metadata (?) to skip saving JSON files
        super().__init__(name, **kwargs)
        self.search_url = self.base_url + self.search_query
        self.logger.info(f"Setting up a {self.name.capitalize()}Spider. params: dump_dir={dump_dir}, update={update}, save_html={save_html}")
        self.files_dumped_counter = 0   # TODO find a different way to measure progress
        
        if dump_dir is None:
            self.logger.warning("dump_dir is None. JSON/HTML files will not be saved!")
            self.dump_dir = dump_dir
            # NOTE maybe just stop the spider right now? and avoid the trouble of checking it it's None...
        elif os.path.exists(dump_dir):
            if os.path.isdir(dump_dir):
                self.dump_dir = dump_dir
            else:
                self.logger.critical("Invalid dump_dir (not a directory). Setting dump_dir to None. JSON/HTML files will not be saved!")
                self.dump_dir = None
        else:
            self.dump_dir = dump_dir
            os.makedirs(dump_dir)

        if start_page is not None:
            start_url = self.search_url + str(start_page)
            self.start_page = int(start_page)
        else:
            start_url = self.search_url + "0"   # starts from page number 0 by default
            self.start_page = 0
        self.stop_page = stop_page  # is handled in `parse`
        self.update = update.lower() in ("yes", "y", "true", "t", "1")
        self.save_html = self.dump_dir is not None and save_html.lower() in ("yes", "y", "true", "t", "1")
        self.start_urls = [start_url]
        
    def parse(self, response):
        """Follows on results for the search query (search pages). 
        
        If `stop_page` was not provided by user, it first calls `learn_search_pages` and iterates over all pages in the range.
        """        
        if self.stop_page is None:
            # find out how many pages is possible to scrape
            stop_page = self.learn_search_pages(response)
            # spider will if not run it's impossible to find the number of all search pages from the start_url!
            assert stop_page is not None
        else:
            stop_page = int(self.stop_page)
        self.logger.info(f"Now starting to crawl through searchpages. start_page={self.start_page}, stop_page={stop_page}")
        for i in range(self.start_page, stop_page):
            page = self.search_url + str(i)   # possibly i+1?
            yield response.follow(page, callback=self.parse_searchpage)
        
    def parse_searchpage(self, response):
        """Should find links from a searchpage and then use other spider functions
        
        for example `yield response.follow(page, callback=self.parse_article)`
        or `yield response.follow(page, callback=self.parse_metadata)`
        """
        raise NotImplementedError

    def parse_article(self, response):
        raise NotImplementedError
    
    def parse_metadata(self, response) -> dict:
        """Should parse an article's webpage and return a dictionary with its metadata.

        The result should be a JSON-like dictionary containing keys like 'doi' or 'has_reviews'. See article_schema.json
        """
        raise NotImplementedError
    
    def learn_search_pages(self, response) -> int | None:
        """Should find how many pages of results there are for the search query

        This function is called in `parse` in its default implementation.

        Returns:
            An integer value or None if unsuccesful.
        """
        raise NotImplementedError
    
    def dump_metadata(self, metadata, dirname=None, filename='metadata', overwrite=None):
        """Takes a dictionary containing article metadata and saves it to a JSON file in `self.dump_dir`.

        Args:
            metadata (dict): dictionary to be saved to file.
            dirname (str, optional): If specified, a directory with the provided name will be created inside `self.dump_dir` (if it doesn't exist) and the metadata is saved there. Defaults to None.
            filename (str, optional): Base file name (without an extension). Defaults to 'metadata', so the output file will be named metadata.json.
            overwrite (bool, optional): Should file be overwritten if it exists already? Defaults to None, which defaults to `self.update`.
        """
        assert self.dump_dir is not None
        if dirname is None:
            dirpath = self.dump_dir
        else:
            dirpath = os.path.join(os.path.abspath(self.dump_dir), dirname)
        os.makedirs(dirpath, exist_ok=True)
        
        if overwrite is None:
            overwrite = self.update
        
        self.logger.debug(f"Saving metadata to file in {dirpath}.")
        filepath = f"{os.path.join(dirpath, filename)}.json"
        f_exists = os.path.exists(filepath)
        dump = not f_exists or (f_exists and overwrite)

        try:
            if f_exists and not overwrite:
                self.logger.debug(f"metadata already exists in {dirpath}. Will NOT overwrite.")
            elif f_exists and overwrite:
                self.logger.warning(f"metadata already exists in {dirpath}. Will overwrite.")
            if dump:
                with open(filepath, 'w', encoding="utf-8") as fp:
                    json.dump(metadata, fp, ensure_ascii=False)
        except Exception as e:
            self.logger.exception(f"Problem while saving to file: {filepath}.\n{e}")
        else:
            if dump:
                self.logger.info(f"Saved metadata to {dirname}\{filename}.json")
                self.files_dumped_counter += 1
            
    def dump_html(self, response, dirname=None, filename='webpage', overwrite=None):
        """Save a response in text format to a HTML file in `self.dump_dir`.

        Removes 'script', 'style', 'noscript', 'link', 'rect' tags and comments from the HTML.
        Args:
            response: # NOTE maybe string html should be the argument after all...
            dirname (str, optional): If specified, a directory with the provided name will be created inside `self.dump_dir` (if it doesn't exist) and the metadata is saved there. Defaults to None.
            filename (str, optional): Base file name (without an extension). Defaults to 'webpage', so the output file will be named webpage.html.
            overwrite (bool, optional): Should file be overwritten if it exists already? Defaults to None, which defaults to `self.update`.
        """
        if not self.save_html:
            return
        assert self.dump_dir is not None
        if dirname is None:
            dirpath = self.dump_dir
        else:
            dirpath = os.path.join(os.path.abspath(self.dump_dir), dirname)
        os.makedirs(dirpath, exist_ok=True)
        
        if overwrite is None:
            overwrite = self.update

        self.logger.debug(f"Saving HTML to text file in {dirpath}.")
        filepath = f"{os.path.join(dirpath, filename)}.html"
        f_exists = os.path.exists(filepath)
        dump = not f_exists or (f_exists and overwrite)

        if f_exists and not overwrite:
            self.logger.debug(f"HTML file already exists in {dirpath}. Will NOT overwrite.")
        elif f_exists and overwrite:
            self.logger.info(f"HTML file already exists in {dirpath}. Will overwrite.")
        if dump:
            # clean up the html: code by Kim Hyesung on https://stackoverflow.com/questions/40529848/how-to-write-the-output-to-html-file-with-python-beautifulsoup
            soup = BeautifulSoup(response.text)
            [x.extract() for x in soup.find_all('script')]
            [x.extract() for x in soup.find_all('style')]
            # [x.extract() for x in soup.find_all('meta')]  # actually better to keep meta because it contains some data...
            [x.extract() for x in soup.find_all('noscript')]
            [x.extract() for x in soup.find_all('link')]
            [x.extract() for x in soup.find_all('rect')]
            [x.extract() for x in soup.find_all(text=lambda text:isinstance(text, Comment))]
            with open(filepath, mode = 'w', encoding = 'utf-8') as fp:
                fp.write(str(soup).replace('\n\n','\n'))
            self.logger.info(f"Saved HTML file to {dirname}\{filename}.html")
            self.files_dumped_counter += 1
