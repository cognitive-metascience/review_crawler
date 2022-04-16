
"""test crawler for going through the PLOS website and the `allofplos_xml.zip` file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into subdirectories in `plos/reviewed_articles`.
Additionally, the sub-articles (reviews and such) from each xml are extracted and saved into files.
Parsed metadata about each article in the zip file is saved to `plos/all_articles` directory
"""

import json
import logging
import os
import zipfile
import lxml.etree as et

from allofplos.allofplos.article import Article
from allofplos.allofplos.plos_regex import validate_plos_url

from utils import cook, get_logger

# globals:
crawler_dir = os.path.abspath(os.path.dirname(__file__))

# paths relative to `crawler_dir`, this is where parsed data is saved
ALL_ARTICLES_DIR = 'plos/all_articles' 
FILTERED_DIR = 'plos/reviewed_articles'

zipfile_path = os.path.join(crawler_dir, 'allofplos_xml.zip')   # NOTE: subject to change
all_articles_path = os.path.join(crawler_dir, ALL_ARTICLES_DIR)
filtered_path = os.path.join(crawler_dir, FILTERED_DIR)

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
json_logfile = os.path.join(logs_path, 'plos_lastrun.json')
logger = get_logger("plosLogger", logs_path)


def _shorten(url):  
    if not validate_plos_url(url):
        logger.warning(f"{url} was deemed an invalid url.")
    elif 'article' or 'peerReview' in url: return (url.split('/')[-1])
    else: return url


def get_metadata_from_url(url, dump_dir=None):
    """
    Parses a PLOS article with the given url. Saves output to a JSON file if dump_dir is specified.

    :type dump_dir: str
    :type url: str
    :return: dict containing scraped metadata
    :rtype: dict
    """

    if not validate_plos_url(url):
        raise Exception("Invalid url for get_metadata_from_url.")

    metadata = {'url': url}
    logger.info(f"Parsing: {url}.")

    try:
        soup = cook(url)

        raise NotImplementedError() # todo

    except Exception as e:
        logger.warning(f"There was a {e.__class__.__name__} while parsing article {_shorten(url)}: {e}\narticle metadata: {metadata}")

    else:
        logger.info(f"Parsed {(url)} succesfully.")
        if dump_dir is not None:
            logger.info("Saving to file.")
            try:
                filename = f"{os.path.join(dump_dir, _shorten(url))}.json"
                if os.path.exists(filename):
                    logger.warning(f"{_shorten(url)}.json already exists in dump_dir. Will NOT overwrite.")
                else:
                    with open(filename, 'w+', encoding="utf-8") as fp:
                        json.dump(metadata, fp, ensure_ascii=False)
            except Exception as e:
                logger.exception(
                    f"Problem while saving to file: {filename}.\n{e}")
            else:
                logger.info(f"Saved metadata to file.")
    return metadata


def get_metadata_from_xml(root) -> dict:
    """
    TODO: improve this to fit the schema 
    (possibly use allofplos.corpus_analysis.get_article_metadata)
    """
    metadata = {}
    metadata['title'] = root.find('.//title-group').find('article-title').text
    front = root.find('front')
    if not front:
        front = root.find('front-stub') # for sub-articles
    el: et.Element
    for el in front.iter('article-id'): 
        metadata[el.attrib['pub-id-type']] = el.text
    return metadata

def parse_zipped_article(fp, update = False):
    """
    Parses a file that's assumed to be inside `allofplos_xml.zip`.

    If parameter `update` is set to `True`, files will be created and overwritten inside `FILTERED_DIR` and `

    :type fp: file-like (readable object)
    :return: dictionary object containing parsed metadata
    :rtype: dict
    """
    raise NotImplementedError() # TODO


def process_allofplos_zip(update = False, print_logs=False):
    """
    Assumes that 'allofplos_xml.zip' file is present in this script's folder. Goes through the zip file contents and extracts XML files for reviewed articles, as well as some metadata.
    The XML files and JSON files containing metadata are saved into subdirectories named after the article's DOI.
    Sub-articles (reviews, decision letters etc.) are saved to subdirectories named 'sub-articles'.
    If the parameter `update` is set to `True`, files in `FILTERED_DIR` will be overwritten.
    
    """
    if print_logs:
        logger.parent.handlers[0].setLevel(logging.INFO)

    logger.debug('setting up a PLOScrawler to go through allofplos_xml.zip')

    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    zipf = zipfile.ZipFile(zipfile_path, 'r')
    for filename in zipf.namelist():
        if not update and os.path.exists(os.path.join(all_articles_path, os.path.splitext(filename)[0]+".json")):
            # skipping files that were already parsed
            logging.debug(f'Skipping {filename} as it was already parsed.')
            continue

        logger.info(f'Processing {filename}')
        fp = zipf.open(filename)
        a = Article.from_xml(fp.read())
        fp.close()

        metadata = get_metadata_from_xml(a.root)

        # assuming if sub-articles are present, then there are reviews
        if len(a.get_subarticles()) > 0:
            metadata["has_reviews"] = True
            article_dir = os.path.join(filtered_path, os.path.splitext(filename)[0])
            if os.path.exists(article_dir) and not update:
                logger.info('Skipping because We already have this article in reviewed_articles.')
            else:
                logging.info('This article probably has reviews. Saving it to reviewed_articles.')
                os.makedirs(article_dir, exist_ok=True)
                # save the XML
                a.tree.write(os.path.join(article_dir, filename))
                # save metadata
                with open(os.path.join(article_dir, "metadata.json"), 'w+') as fp:
                    json.dump(metadata, fp)
            
                # iterate over sub-articles
                for sub_a in a.get_subarticles():
                    subtree = et.ElementTree(sub_a)
                    doi = subtree.find('.//article-id').text
                    path = os.path.join(article_dir, "sub-articles", doi.split('/')[-1]+'.xml')
                    if not os.path.exists(os.path.join(article_dir, "sub-articles")):
                        os.mkdir(os.path.join(article_dir, "sub-articles"))
                    if update or not os.path.exists(path):
                        subtree.write(path)                

        # finally, save metadata to all_articles
        if update or not os.path.exists(os.path.join(all_articles_path, os.path.splitext(filename)[0]+".json")):
            with open(os.path.join(all_articles_path, os.path.splitext(filename)[0]+".json"), 'w+') as fp:
                json.dump(metadata, fp)


if __name__ == '__main__':
    process_allofplos_zip(update = True,
                        print_logs = True)
