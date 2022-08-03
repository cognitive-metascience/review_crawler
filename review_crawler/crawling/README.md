The crawler for the MDPI database consists of two dedicated Scrapy spiders: `mdpi_spider.py` and `mdpi_review_spider.py`. Basic knowledge on how to use Scrapy will be required to run them.

## Installation & usage

Install Scrapy through pip:

`pip install scrapy`

Change working directory to this folder:

`cd review_crawler/crawling`

Run the first spider which finds metadata for all MDPI articles. Use the `dump_dir` parameter to specify the output directory in which JSON files will be stored. By default, the entire MDPI database is searched (so this process might take a long time).

`scrapy crawl mdpi -a dump_dir=../output/mdpi`

Run the second spider which scans the previously dumped metadata and finds reviews:

`scrapy crawl mdpi_review -a dump_dir=../output/mdpi`

____

Coming soon: more detailed usage instructions & additional information on available spider arguments.
