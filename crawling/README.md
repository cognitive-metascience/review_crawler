The crawler for the MDPI database consists of two dedicated Scrapy spiders: `mdpi_spider.py` and `mdpi_review_spider.py`. Basic knowledge on how to use Scrapy will be required to run them.

## Installation & usage

Install Scrapy through pip:

```pip install scrapy```

Make sure to change your working directory to this folder:

```cd review_crawler/crawling```

Run the first spider which finds metadata for all MDPI articles. Use the `dump_dir` parameter to specify the output directory in which JSON files will be stored. By default, the entire MDPI database is searched (so this process might take a very long time).

```scrapy crawl mdpi -a dump_dir=../output/mdpi```

Run the second spider which scans the previously dumped metadata and finds reviews:

```scrapy crawl mdpi_review -a dump_dir=../output/mdpi```

### Optional arguments

These spiders have additional arguments that can be specified on the command line by using the `-a` flag.

#### Arguments available for both `mdpi_spider` and `mdpi_review_spider`:

- `dump_dir` - as illustrated above, this directory will be where the output of `mdpi_spider` is saved. This same argument is used as input by `mdpi_review_spider`. If `dump_dir` is not specified, the spider output will not be saved locally, unless you use one of [the `-o/-O` flags](https://docs.scrapy.org/en/latest/topics/commands.html#crawl). It's probably best to not use `-o/-O` flags and the `dump_dir` argument at the same time.

- `update` - whether existing files should be updated (overwritten). Defaults to "no". Override by passing one of ("yes", "true", "t", "1"). 

  For example:

  ```scrapy crawl mdpi -a dump_dir=../output/mdpi -a update=1```

#### Available `mdpi_spider` arguments:

- `year_from` and `year_to` - provide a four-digit string to narrow down the search. 

  For example: 

  ```scrapy crawl mdpi -a dump_dir=../output/mdpi -a year_from=2012 -a year_to=2022```

- `journal` - narrow down the search by specifying which of MDPI journals' database should be scraped. Only one can be specified. Find the list of accepted abbrevations [here](../scraped/mdpi/journals.json). 

  For example, in order to scrape only the articles from "Environmental Sciences Proceedings": 

  ```scrapy crawl mdpi -a dump_dir=../output/mdpi -a journal=environsciproc```

- `start_page` and `stop_page` - specify how many search pages should be scraped. If not provided, defaults to all search pages.


#### Available `mdpi_review_spider` arguments:

- `url` - can be provided instead of the `dump_dir` argument, in order to scrape reviews from just one specific article.

  For example:

  ```scrapy crawl mdpi_review -a url=https://www.mdpi.com/2032-6653/12/4/191```

### After scraping

See the Jupyter Notebooks located in the `review_crawler` directory for steps on handling the scraped corpus. Some operations that need to be performed after running the spiders:

- [calculate basic statistics and add sub-article metadata to `metadata.json` files](../file_management.ipynb)
- [assign supplementary-materials to the correct rounds of reviews](../fix_suppms.ipynb)

## Known issues

Some articles' web pages have a non-standard HTML structure, which the mdpi_review_spider cannot (yet) handle. You may notice AttributeError or KeyError occuring when trying to parse these pages. For these articles, you may find that the 'sub-articles' directory is created, but stays empty.

In other cases, the spider may have issues extracting the data for all rounds of reviews (e.g. only 2 out of 3).
____


## Next steps

- finalizing the MDPI corpus by scraping all remaining article metadata files

- use the Crossref API to find which DOIs are missing from the corpus

- handle special cases that cause some articles to be incorrectly scraped (see the 'Known issues' section)

- move some functions that do file management from Jupyter notebooks to the Scrapy project. For example, to handle adding sub-article metadata using [Item Exporters](https://docs.scrapy.org/en/latest/topics/exporters.html) or [Spider Middleware](https://docs.scrapy.org/en/latest/topics/spider-middleware.html)
