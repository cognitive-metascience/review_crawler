
## Installation & usage

Clone this repository:

```git clone https://github.com/cognitive-metascience/review_crawler.git```

 and change your working directory to this folder:

```cd review_crawler```

Then install the required Python packages:

```pip install -r requirements.txt```

### PLOS crawler
> this crawler uses the [__allofplos__](https://doi.org/10.25080/Majora-4af1f417-009) library to parse and extract metadata from articles in the PLOS corpus. This database is stored in a ZIP file which will be downloaded to your local storage before you run the crawler for the first time. **Be warned:** as of 15 August 2023, this zip archive contains nearly 8 GB of data: articles in JATS-standard XML format. 

First, make sure your current working directory is set to `/review_crawler`, like above. 

Run the following command to download [this fork](https://github.com/x-j/allofplos) the __allofplos__, which is necessary to run `plos_crawler`:

```git submodule update --init allofplos```


The first time you run the crawler, you will need to use the `--download` flag  in order to download the PLOS corpus on your device, like in the example below:

```python -m plos_crawler --download```

Alternatively, you can manually download the PLOS corpus from [this link](https://allof.plos.org/allofplos.zip). Place the downloaded file into the folder `review_crawler/input`, without changing its filename.

Again, *keep in mind* that the downloaded zip file will be very huge in size. Please make sure you have sufficient amount of free space before hitting *enter*. 

The crawler will take its time time to process all this data. Eventually you should find the results in the `output/plos` folder:
-  metadata for all articles in JSON format in the folder `all_articles`, 
- in the folder `reviewed_articles`: subfolders for each reviewed article, metadata in JSON, the article itself in XML, and a subfolder `sub-articles` containing metadata and XMLs of reviews, decision letters, author responses, as well as any supplementary materials (usually DOCX and PDF files).

### eLife crawler

This crawler is very similar to the one for PLOS, as both are parsing articles in JATS format. This one also utilises some parts of the __allofplos__ library, so it's necessary to initialize the submodule first, like above.

Download a zip file containing the eLife corpus directly from [their GitHub repository](https://github.com/elifesciences/elife-article-xml) (click on 'Code' -> 'download ZIP') and place it in the `review_crawler/input` folder without changing its filename.

Alternatively, you can clone the entire __elife-article-xml__ submodule which contains uncompressed articles in XML (the corpus is updated daily and as of 27th of July 2022, it contains nearly 3 GB of data). In this case use the following command:

```git submodule update --init elife-article-xml```

Run the crawler from the command line like this:

```python -m elife_crawler```

In the `output/elife` folder you should find the results, in the same format as the ones for PLOS.

### MDPI crawler

Consists of two dedicated [__Scrapy__](https://scrapy.org) spiders. For usage instructions, consult the [Readme file in the `crawling`](crawling/) directory which contains the Scrapy project. 

## License

BSD-2-Clause. See the [LICENSE.txt](/review_crawler/LICENSE.txt) file.
