Uses the [__allofplos__](https://doi.org/10.25080/Majora-4af1f417-009) Python package to parse and extract metadata from articles in PLOS database.

## Installation & usage

After cloning the parent repository, change working directory to this folder:

```cd review_crawler```

Install required Python packages:

```pip install -r requirements.txt```

The following command clones the __allofplos__ fork, which is necessary to run `plos_crawler`, and also downloads the entire eLife corpus from the __elife-article-xml__ repo (be warned: this corpus contains nearly 3 GB of data!):

```git submodule update --init```




### PLOS crawler

First, make sure your current working directory is set to `/review_crawler`, like above. 

Run the following command to clone the __allofplos__ fork, which is necessary to run `plos_crawler`:

```git submodule update --init allofplos```

Download the PLOS corpus from [this link](https://drive.google.com/a/plos.org/uc?id=0B_JDnoghFeEKLTlJT09IckMwOFk). Be warned, because as of 27th of July 2022, this zip archive contains nearly 5 GB of data: articles in JATS-standard XML format. Place the downloaded zip into the folder `input`, without changing its filename. 

Alternatively, you can use the `download_allofplos_zip` function from `plos_crawler` to download the corpus.

Run the crawler from the command line like this:

```python -m plos_crawler```

You can expect it to take some time to process nearly 5 GB of XMLs. Eventually you should find the results in the `output/plos` folder:
-  metadata for all articles in JSON format in the folder `all_articles`, 
- in the folder `reviewed_articles`: subfolders for each reviewed article, metadata in JSON, the article itself in XML, and a subfolder `sub-articles` containing metadata and XMLs of reviews, decision letters, author responses, as well as any supplementary materials (usually DOCX and PDF files).

### eLife crawler

This crawler is very similar to the one for PLOS, as both are parsing articles in JATS format. This one also utilises some parts of the __allofplos__ library, so it's necessary to initialize the submodule first, like above.

Download a zip file containing the eLife corpus directly from [their GitHub repository](https://github.com/elifesciences/elife-article-xml) (click on 'Code' -> 'download ZIP') and place it in the `input` folder without changing its filename.

Alternatively, you can clone the entire __elife-article-xml__ submodule which contains uncompressed articles in XML (the corpus is updated daily and as of 27th of July 2022, it contains nearly 3 GB of data). In this case use the following command:

```git submodule update --init elife-article-xml```

Run the crawler from the command line like this:

```python -m elife_crawler```

In the `output/elife` folder you should find the results, in the same format as the ones for PLOS.

### MDPI crawler

Consists of two dedicated [__Scrapy__](https://scrapy.org) spiders. For usage instructions, consult the [Readme in the `crawling`](/review_crawler/crawling/) directory which contains the Scrapy project. 
