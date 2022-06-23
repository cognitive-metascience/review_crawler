
"""test crawler for going through the `allofplos_xml.zip` file. The zip file will be downloaded to `allofplos` directory.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into subdirectories in `plos/reviewed_articles`.
Additionally, the sub-articles (reviews and such) from each xml are extracted and saved into files.
Parsed metadata about each article in the zip file is saved to `plos/all_articles` directory
"""

import json
import logging
import os
import requests
import lxml.etree as et

from zipfile import ZipFile, BadZipFile

from allofplos.allofplos.article import Article
from allofplos.allofplos.corpus.gdrive import unzip_articles
from allofplos.allofplos.corpus.plos_corpus import create_local_plos_corpus
from allofplos.allofplos.plos_regex import validate_doi, validate_plos_url

from utils import cook, get_extension_from_str, get_logger

# globals:
crawler_dir = os.path.abspath(os.path.dirname(__file__))

# paths relative to `crawler_dir`, this is where parsed data is saved
ALL_ARTICLES_DIR = 'scraped/plos/all_articles' 
FILTERED_DIR = 'scraped/plos/reviewed_articles'

zipfile_dir = os.path.join(crawler_dir, 'allofplos')   # NOTE: subject to change
zipfile_path = os.path.join(zipfile_dir, 'allofplos_xml.zip') 

all_articles_path = os.path.join(crawler_dir, ALL_ARTICLES_DIR)
filtered_path = os.path.join(crawler_dir, FILTERED_DIR)

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
json_logfile = os.path.join(logs_path, 'plos_lastrun.json')
logger = get_logger("plosLogger", logs_path)


def url_to_doi(url) -> str:
    """
    Produces pretty much the same behavior as `allofplos.transformations.url_to_doi`, 
    but also validates the provided url using `validate_plos_url`.

    :return: unique identifier for a PLOS article, review, or other resource
    """  
    if validate_plos_url(url):  return (url.split('?')[1][3:])
    else: 
        logger.warning(f"{url} was deemed an invalid url.")
        return url

def shorten_doi(doi) -> str:
    """
    Returns the tail element of a doi string (that is, everything after the last slash).
    The provided DOI is validated using regex from `allofplos` library.
    """
    if validate_doi(doi): return doi.split('/')[-1]
    else:
        logger.warning(f"{doi} was deemed an invalid doi.")
        return doi

def download_allofplos_zip(unzip=False):
    """
    Calls `create_local_plos_corpus` to download the entire PLOS database contained in a zip file.
    The zip file will be at least 5 GB heavy, it will be downloaded to directory `zipfile_dir`.

    :param unzip: whether to extract all article files to corpus dir, or just keep the zip file instead. 
    Defaults to `False`, because after extraction, the folder will be around 30 GB heavy.
    """
    # code below is copied from `download_file_from_google_drive()` function from `allofplos.gdrive`
    # check for existing incomplete zip download. Delete if invalid zip.
    if os.path.isfile(zipfile_path) and get_extension_from_str(zipfile_path).lower() == '.zip':
        logger.info("allofplos_xml.zip already exists. Checking if the archive is corrputed or otherwise invalid. This may take some time.")
        try:
            zip_file = ZipFile(zipfile_path)
            if zip_file.testzip():
                os.remove(zipfile_path)
                logger.info("Deleted corrupted previous zip download.")
        except BadZipFile as e:
            os.remove(zipfile_path)
            logger.info("Deleted invalid previous zip download.")
    if os.path.isfile(zipfile_path):
        logger.info("Everything OK with the existing zip file.")
    else:
        logger.info(f"Will attempt to download the allofplos_xml.zip to {os.path.abspath(zipfile_dir)}.")
        create_local_plos_corpus(zipfile_dir, unzip=False, delete_file=False)
        logger.info(f"Finished with download.")
    if unzip:
        logger.info(f"Articles will now be extracted to default corpus directory in {zipfile_dir}")
        unzip_articles(file_path=zipfile_path, delete_file=False)
        
        
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
        logger.warning(f"There was a {e.__class__.__name__} while parsing article {url_to_doi(url)}: {e}\narticle metadata: {metadata}")

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

def check_if_article_retracted(url):
    # TODO: change this to work on Soups?
    soup = cook(url)
    return 'has RETRACTION' in soup.text

def get_metadata_from_xml(root) -> dict:
    """
    Outputs some metadata from the given Element object.
    This function should get the doi right, at the least.
    """
    metadata = {}
    # the line below has problems parsing titles that contain HTML tags, instead Article.authors will be used
    # metadata['title'] = root.find('.//title-group').find('article-title').text    
    front = root.find('front')
    if front is None:
        front = root.find('front-stub') # for sub-articles
    el: et.Element
    for el in front.iter('article-id'): 
        try:
            metadata[el.attrib['pub-id-type'].replace('-', '_')] = el.text.strip()
        except Exception as e:
            logger.error(f"get_metadata_from_xml had a problem with iterating over article-id in front.\n{e}")

    
    return metadata

def get_subarticle_metadata_from_xml(root) -> dict:
    metadata = {}
    front = root.find('front-stub')
    body = root.find('body')

    metadata['type'] = root.attrib['article-type']
    try:
        metadata['specific_use'] = root.attrib['specific-use']
    except KeyError:
        pass

    if metadata['type'] == 'aggregated-review-documents':
        metadata['round'] = int(front.find('.//article-title').text.strip().split()[-1])
    metadata['doi'] = front.find('article-id').text.strip()
    metadata['id']  = shorten_doi(metadata['doi']) # id's are the DOI, shortened
    related_article = front.find('related-object')
    if related_article is not None and related_article.attrib['link-type'] == 'peer-reviewed-article':
        metadata['original_article_doi'] = related_article.attrib['document-id']
    metadata['date'] = body.find('.//named-content').text.strip()

    # find reviewers:
    if metadata['type'] == 'aggregated-review-documents':
        fr = False
        reviewers = []
        for text in [p.text for p in body if p.text]:
            if 'identity' in text: fr = True
            elif fr and 'Reviewer #' in text:
                r = {}
                splat = text.split(':')
                r['number'] = int(splat[0][-1])
                if 'No' in splat[1]: r['name'] = "Anonymous"
                elif 'Yes' in splat[1] and len(splat) > 2:
                    r['name'] = splat[2].strip()
                reviewers.append(r)
        metadata['reviewers'] = reviewers

    # find supplementary materials:
    supplementary = []
    for elem in body.findall('supplementary-material'):
        sm = {'id': ('journal.'+elem.attrib['id']), # these will be in "short" doi format
              'original_filename': elem.find('.//named-content').text}
        sm['url'] = "https://doi.org/10.1371/" + sm['id']
        sm['filename'] = sm['id'] + get_extension_from_str(sm['original_filename'])
        supplementary.append(sm)

    supplementary.append({
        'filename': metadata['id'] + '.xml', 'id': metadata['id'],
        'title': "This sub-article in XML"
    })
    metadata['supplementary_materials'] = supplementary
    return metadata


def parse_article_xml(xml_string: str, update = False, skip_sm_dl = False) -> dict:
    """
    Parses an XML string that's assumed to contain a PLOS article.
    This function relies on the `Article` class from `allofplos` library to extract metadata from XML.
    
    JSON files containing parsed metadata are stored in `ALL_ARTICLES_DIR`.
    Files containing reviewed articles, their sub-articles and supplementary materials are saved to sub-directories in `FILTERED_DIR`. 
    Metadata in JSON format is also saved there. 

    :param xml_string: XML-encoded string containing a PLOS article.
    :param update: if set to `True`, existing files will be overwritten.
    :param skip_supplementary: whether to skip downloading supplementary materials from the PLOS database.
    :return: dictionary object containing parsed metadata
    :rtype: dict
    """
    a = Article.from_xml(xml_string)
    a_short_doi = shorten_doi(a.doi)
    # parse some metadata from the xml itself
    metadata = get_metadata_from_xml(a.root)
    # get metadata from Article object:
    metadata['title'] = a.title
    metadata['url'] = a.get_page('article')
    metadata['fulltext_xml_url'] = a.url
    metadata['journal'] = {'title': a.journal, 'volume': a.volume, 'issue': a.issue}
    metadata['publication_date'] = {'year': a.pubdate.year,
                                    'month': a.pubdate.month, 
                                    'day': a.pubdate.day}
    metadata['authors'] = a.get_author_names()
    metadata['keywords'] = a.categories
    metadata['retracted'] = False # TODO: change to check_if_article_retracted
    
    # assuming if sub-articles are present, then article was reviewed
    if len(a.get_subarticles()) > 0:
        metadata['has_reviews'] = True
        metadata['reviews_url'] = a.get_page('peerReview')
        metadata['sub_articles'] = []
        
        article_dir = os.path.join(filtered_path, a_short_doi)
        sub_articles_dir = os.path.join(article_dir, 'sub-articles')
        logger.info(f'this article probably has reviews! It will be saved to {FILTERED_DIR}.')
        write_files = True
        if not os.path.exists(article_dir):
            os.makedirs(article_dir, exist_ok=False)
        elif update:
            logger.warning(f"files for article {a_short_doi} and its sub-articles already exist in {FILTERED_DIR} and will be overwritten.")
        else:
            write_files = False
        logger.debug("Parsing sub-articles...")
        # iterate over sub-articles
        for sub_a in a.get_subarticles():
            subtree = et.ElementTree(sub_a)
            sub_a_metadata = get_subarticle_metadata_from_xml(sub_a)
            if 'specific_use' in sub_a_metadata.keys():
                if sub_a_metadata['specific_use'] == 'acceptance-letter':
                    # skipping those to save space and time
                    continue
            metadata['sub_articles'].append(sub_a_metadata)
            # find a warning (if any)
            boxed_text = subtree.find('.//boxed-text')
            if boxed_text is not None:
                logger.warning(f"{boxed_text.find('.//title').text.strip()} in {sub_a_metadata['doi']}:\n{boxed_text.find('.//p').text.strip()}")
            if write_files:
                # save this sub-article
                sub_a_path = os.path.join(sub_articles_dir, sub_a_metadata['id'] + '.xml')
                if not os.path.exists(sub_articles_dir):
                    os.mkdir(sub_articles_dir)
                # save the XML:
                subtree.write(sub_a_path)
                # save metadata:
                with open(os.path.join(sub_articles_dir, sub_a_metadata['id'] + '.json'), 'w+') as fp:
                    json.dump(sub_a_metadata, fp)
                # download supplementary materials (if any)
                if not skip_sm_dl and 'supplementary_materials' in sub_a_metadata.keys():
                    for sm in sub_a_metadata['supplementary_materials']:
                        if 'url' not in sm.keys():
                            continue
                        with open(os.path.join(sub_articles_dir, sm['filename']), 'wb') as fp:
                            logger.info(f"Downloading supplementary material from {sm['url']}")
                            r = requests.get(sm['url'], stream=True)
                            fp.write(r.content)
                logger.debug(f"sub-article {sub_a_metadata['doi']} saved to {FILTERED_DIR}/{a_short_doi}")
            
        if write_files:
            # save this article's XML
            a.tree.write(os.path.join(article_dir, a.filename))
            # save metadata to the same directory
            with open(os.path.join(article_dir, "metadata.json"), 'w+') as fp:
                json.dump(metadata, fp)
    else:
        metadata['has_reviews'] = False

    # finally, save metadata to all_articles
    _filename = os.path.join(all_articles_path, a_short_doi + ".json")
    if update or not os.path.exists(_filename):
        with open(_filename, 'w+') as fp:
            json.dump(metadata, fp)
        logger.debug(f"metadata for {a_short_doi} saved to {ALL_ARTICLES_DIR}.")
    return metadata


def process_allofplos_zip(update = False, reviewed_only = True):
    """
    Goes through the zip file contents and extracts XML files for reviewed articles, as well as metadata.
    For each article in the zip, metadata is extracted and stored in a JSON file in `ALL_ARTICLES_DIR`. 
    These files will be overwritten if the flag `update` is set to `True`.
    
    The XML files and JSON files containing reviewed articles and their metadata are saved into subdirectories named after the article's DOI.
    Sub-articles (reviews, decision letters etc.) are saved to subdirectories named 'sub-articles'.
    
    :param update: if is set to `True`, already existing files will be overwritten. Otherwise (and by default), files that were already parsed are skipped.
    :param reviewed_only:  if set to `True`, and if `update` is also `True`, then only articles that already have a directory in `FILTERED_DIR` will be processed
    """

    logger.debug(f'setting up a PLOScrawler to go through allofplos_xml.zip | update = {update} | reviewed_only = {reviewed_only}')

    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    reviewed_counter = 0
    errors_counter = 0 

    allofplos_zip = ZipFile(zipfile_path, 'r')
    for filename in allofplos_zip.namelist():
        try:
            a_short_doi = os.path.splitext(filename)[0]
            metadata_file_exists = os.path.exists(os.path.join(all_articles_path, a_short_doi +".json"))
            # skipping files that were already parsed:
            if not reviewed_only:
                if metadata_file_exists and not update and not a_short_doi in os.listdir(filtered_path):    # NOTE: reviewed articles are NEVER skipped
                    logger.debug(f'Skipping {filename} as it was already parsed.')
                    continue
                elif metadata_file_exists and update:
                    logger.warning(f"file with metadata for {a_short_doi} already exists in {ALL_ARTICLES_DIR} and will be overwritten.")
            if not os.path.exists(os.path.join(filtered_path, a_short_doi)) and reviewed_only:
                logger.debug(f'Skipping {filename} as it probably does not have reviews.')
                continue
            logger.info(f'Processing {filename}')
            fp = allofplos_zip.open(filename)
            a_xml = fp.read()
            fp.close()

            a_metadata = parse_article_xml(a_xml, update = update)
            if a_metadata['has_reviews']: reviewed_counter += 1
            
        except Exception as e:
            errors_counter += 1
            logger.warning(f"There was a {e.__class__.__name__} while parsing {filename} from zip: {str(e)}")
            raise e
        
    logger.info(f"Finished parsing allofplos_xml.zip with {errors_counter} errors encountered in the meantime.")
    logger.info(f"found {reviewed_counter} reviewed articles.")

if __name__ == '__main__':
    # set logging:
    logger.parent.handlers[0].setLevel(logging.INFO)
    # download_allofplos_zip(unzip = False)
    process_allofplos_zip(update = True, reviewed_only=True)
