
"""test crawler for going through the PLOS website and the `allofplos_xml.zip` file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into subdirectories in `plos/reviewed_articles`.
Additionally, the sub-articles (reviews and such) from each xml are extracted and saved into files.
Parsed metadata about each article in the zip file is saved to `plos/all_articles` directory
"""

import json
import logging
import os
import requests
import zipfile
import lxml.etree as et

from allofplos.allofplos.article import Article
from allofplos.allofplos.corpus.plos_corpus import create_local_plos_corpus, download_check_and_move, get_dois_needed_list
from allofplos.allofplos.plos_regex import validate_doi, validate_plos_url

from utils import cook, get_logger

# globals:
crawler_dir = os.path.abspath(os.path.dirname(__file__))

# paths relative to `crawler_dir`, this is where parsed data is saved
ALL_ARTICLES_DIR = 'plos/all_articles' 
FILTERED_DIR = 'plos/reviewed_articles'

zipfile_dir = os.path.join(crawler_dir, 'allofplos')   # NOTE: subject to change
zipfile_path = os.path.join(zipfile_dir, 'allofplos_xml.zip') 

all_articles_path = os.path.join(crawler_dir, ALL_ARTICLES_DIR)
filtered_path = os.path.join(crawler_dir, FILTERED_DIR)

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
json_logfile = os.path.join(logs_path, 'plos_lastrun.json')
logger = get_logger("plosLogger", logs_path)


def url_to_doi(url):
    """
    Produces pretty much the same behavior as `allofplos.transformations.url_to_doi`, 
    but also validates the provided url using `validate_plos_url`.

    :return: unique identifier for a PLOS article, review, or other resource
    """  
    if validate_plos_url(url):  return (url.split('?')[1][3:])
    else: 
        logger.warning(f"{url} was deemed an invalid url.")
        return url

def _shorten_doi(doi):
    if validate_doi(doi): return doi.split('/')[-1]
    else:
        logger.warning(f"{doi} was deemed an invalid doi.")
        return doi

def download_allofplos_zip():
    """
    Calls `create_local_plos_corpus` to download the entire PLOS database contained in a zip file.
    The zip file will be at least 5 GB heavy, it will be downloaded to directory `zipfile_path`.
    """
    logger.info(f"Will attempt to download the allofplos_xml.zip to {os.path.abspath(zipfile_dir)}.")
    create_local_plos_corpus(zipfile_dir, rm_metadata=True, unzip=True, delete_file=False)
        

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
    TODO: improve this to fit the schema 
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
        metadata[el.attrib['pub-id-type'].replace('-', '_')] = el.text
    
    # get keywords: TODO move this to Article class
    keywords_set = set()    # using a set because they tend to be duplicated
    categories = front.find('.//article-categories')
    if categories is None:
            return metadata

    for el in categories[1:]:   # skipping the first one because it's a "heading"
        for subj in el.iterdescendants():
            if len(subj) == 1:
                keywords_set.add(subj[0].text)
    metadata['keywords'] = list(keywords_set)
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
        metadata['round'] = int(front.find('.//article-title').text.split()[-1])
    metadata['doi'] = front.find('article-id').text
    related_article = front.find('related-object')
    if related_article and related_article.attrib['link-type'] == 'peer-reviewed-article':
        metadata['original_article_doi'] = related_article.attrib['document-id']
    metadata['date'] = body.find('.//named-content').text

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
    supplementary_ids = []
    for sm in body.findall('supplementary-material'):
        supplementary_ids.append('journal.'+sm.attrib['id'])   # these will be in "short" doi format
    if len(supplementary_ids) > 0: metadata['supplementary_material_ids'] = supplementary_ids
    return metadata

def get_authors_from_article(authors: list) -> list:
    """
    Transforms a list of dicts produced from Article.authors into a simpler list of author names.
    TODO move this to Article class
    """
    parsed_authors = []
    for author in authors:
        try:
            if author['given_names'] is None and author['surname'] is None:
                parsed_authors.append(author['group_name'])
            else:
                parsed_authors.append(author['given_names']+ ' ' +author['surname'])
        except KeyError or TypeError:
            logger.error(f"Invalid argument passed to function `get_authors_from_article`.\n\
                Expected a list of dicts containing keys `given_names` and `surname`.")
    return parsed_authors


def parse_zipped_article(fp, update = False):
    """
    Parses a file that's assumed to be inside `allofplos_xml.zip`.

    If parameter `update` is set to `True`, files will be created and overwritten inside `FILTERED_DIR`

    :type fp: file-like (readable object)
    :return: dictionary object containing parsed metadata
    :rtype: dict
    """
    raise NotImplementedError() # TODO


def process_allofplos_zip(update = False, print_logs=False):
    """
    Goes through the zip file contents and extracts XML files for reviewed articles, as well as metadata.
    For each article in the zip, metadata is extracted and stored in `ALL_ARTICLES_DIR`
    The XML files and JSON files containing metadata are saved into subdirectories named after the article's DOI.
    Sub-articles (reviews, decision letters etc.) are saved to subdirectories named 'sub-articles'.
    If the parameter `update` is set to `True`, files in `FILTERED_DIR` will be overwritten.
    
    """
    if print_logs:
        logger.parent.handlers[0].setLevel(logging.INFO)

    logger.debug(f'setting up a PLOScrawler to go through allofplos_xml.zip | update = {update}, print_logs = {print_logs}')

    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    reviewed_counter = 0
    errors_counter = 0  #TODO

    allofplos_zip = zipfile.ZipFile(zipfile_path, 'r')
    for filename in allofplos_zip.namelist():
        try:
            a_short_doi = os.path.splitext(filename)[0]
            metadata_file_exists = os.path.exists(os.path.join(all_articles_path, a_short_doi +".json"))
            if metadata_file_exists and not update and not a_short_doi in os.listdir(filtered_path):
                # skipping files that were already parsed
                logger.debug(f'Skipping {filename} as it was already parsed.')
                continue

            logger.info(f'Processing {filename}')
            fp = allofplos_zip.open(filename)
            a = Article.from_xml(fp.read())
            fp.close()

            # parse some metadata from the xml itself
            a_metadata = get_metadata_from_xml(a.root)
            # get metadata from Article object:
            a_metadata['title'] = a.title
            a_metadata['url'] = a.get_page('article')
            a_metadata['fulltext_xml_url'] = a.url
            a_metadata['journal'] = {'title': a.journal, 'volume': a.volume, 'issue': a.issue}
            a_metadata['publication_date'] = {'year': a.pubdate.year,
                                            'month': a.pubdate.month, 
                                            'day': a.pubdate.day}
            a_metadata['authors'] = get_authors_from_article(a.authors)
            a_metadata['retracted'] = False # change to check_if_article_retracted
            
            # assuming if sub-articles are present, then article was reviewed
            if len(a.get_subarticles()) > 0:
                reviewed_counter += 1
                a_metadata["has_reviews"] = True
                article_dir = os.path.join(filtered_path, a_short_doi)
                if os.path.exists(article_dir):
                    logger.warning(f"files for article {a_short_doi} and its sub-articles already exist in {FILTERED_DIR} and will be overwritten.")
                else:
                    logger.info(f'{a_short_doi} probably has reviews. Saving it to {FILTERED_DIR}/{article_dir}.')

                os.makedirs(article_dir, exist_ok=True)

                # save the XML
                a.tree.write(os.path.join(article_dir, filename))
                # save metadata
                with open(os.path.join(article_dir, "metadata.json"), 'w+') as fp:
                    json.dump(a_metadata, fp)
            
                # iterate over sub-articles
                for sub_a in a.get_subarticles():
                    subtree = et.ElementTree(sub_a)
                    sub_a_metadata = get_subarticle_metadata_from_xml(sub_a)
                    if 'specific_use' in sub_a_metadata.keys():
                        if sub_a_metadata['specific_use'] == 'acceptance-letter':
                            # skipping those to save space and time
                            continue
                    
                    # save this sub-article
                    sub_articles_dir = os.path.join(article_dir, "sub-articles")
                    path = os.path.join(sub_articles_dir, _shorten_doi(sub_a_metadata['doi']) + '.xml')
                    if not os.path.exists(sub_articles_dir):
                        os.mkdir(os.path.join(article_dir, "sub-articles"))
                    
                    # save the XML:
                    subtree.write(path)
                    # save metadata:
                    with open(os.path.join(sub_articles_dir, _shorten_doi(sub_a_metadata['doi']) + '.json'), 'w+') as fp:
                        json.dump(sub_a_metadata, fp)
                    # TODO: download supplementary materials (if any)
                    if 'supplementary_material_ids' in sub_a_metadata.keys():
                        for id in sub_a_metadata['supplementary_material_ids']:
                            pass        

                    logger.debug(f"sub-article {sub_a_metadata['doi']} saved to {article_dir}")
            else:
                a_metadata['has_reviews'] = False

            # finally, save metadata to all_articles
            if metadata_file_exists:
                logger.warning(f"file with metadata for {a_short_doi} already exists in {ALL_ARTICLES_DIR} and will be overwritten.")
            with open(os.path.join(all_articles_path, a_short_doi +".json"), 'w+') as fp:
                json.dump(a_metadata, fp)
            logger.debug(f"metadata for {filename} saved succesfully.")
        
        except Exception as e:
            errors_counter += 1
            logger.warning(f"There was a {e.__class__.__name__} while parsing {filename} from zip: {str(e)}")
        
    logger.info(f"Finished parsing allofplos_xml.zip with {errors_counter} errors encountered in the meantime.")
    logger.info(f"found {reviewed_counter} reviewed articles.")

if __name__ == '__main__':
    # download_allofplos_zip()
    process_allofplos_zip(update = False, print_logs = True)
