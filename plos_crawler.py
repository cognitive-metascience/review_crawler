
"""crawler for going through the `allofplos_xml.zip` file. The zip file will be downloaded to `input` directory if the --download-zip.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into subdirectories in `plos/reviewed_articles`.
Additionally, the sub-articles (reviews and such) from each xml are extracted and saved into files.
Parsed metadata about each article in the zip file is saved to `plos/all_articles` directory
"""

import argparse
import json
import os
import requests
import lxml.etree as et
from zipfile import ZipFile

from allofplos.allofplos.article import Article
from allofplos.allofplos.corpus.plos_corpus import download_corpus_zip, unzip_articles
from allofplos.allofplos.plos_regex import validate_doi, validate_plos_url

from utils import cook, get_extension_from_str, get_logger, OUTPUT_DIR, INPUT_DIR


logger = get_logger("plos", fileh_level='DEBUG', streamh_level='INFO')

## DEFAULT PATHS ##

# these paths are relative to `CRAWLER_DIR`, which should be where this script is located
zipfile_dir = INPUT_DIR
zipfile_path = os.path.join(INPUT_DIR, 'allofplos.zip')
default_extract_dir = os.path.join(zipfile_dir, 'allofplos_xml')

# names of folders for where data is saved
ALL_ARTICLES_DIR = os.path.join('plos','all_articles' )
FILTERED_DIR = os.path.join('plos','reviewed_articles')
all_articles_path = os.path.join(OUTPUT_DIR, ALL_ARTICLES_DIR)
filtered_path = os.path.join(OUTPUT_DIR, FILTERED_DIR)



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


def doi_to_short_doi(doi) -> str:
    """
    Returns the tail element of a doi string (that is, everything after the last slash).
    The provided DOI is validated using regex from `allofplos` library.
    """
    if validate_doi(doi): return doi.split('/')[-1]
    else:
        logger.warning(f"{doi} was deemed an invalid doi.")
        return doi


def check_if_article_retracted(url):
    # TODO: change this to work on Soups?
    soup = cook(url)
    return 'has RETRACTION' in soup.text


def parse_subarticle(root) -> dict:
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
    
    # create id out of doi:
    splat = doi_to_short_doi(metadata['doi']).rsplit('.', 1)
    if metadata['type'] == 'author-comment':
        id_str = splat[0]+".a{}"
    else:
        id_str = splat[0]+".r{}"
    metadata['id'] = id_str.format(int(splat[1][1:]))
    
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
    :param skip_sm_dl: whether to skip downloading supplementary materials from the PLOS database.
    :return: dictionary object containing parsed metadata
    :rtype: dict
    """
    a = Article.from_xml(xml_string)
    a_short_doi = doi_to_short_doi(a.doi)
    metadata = {}
    # get metadata from Article object:
    metadata['doi'] = a.doi
    metadata['title'] = a.title
    metadata['url'] = a.page
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
        logger.info(f'Article {a_short_doi} probably has reviews! Full metatada will be saved to {FILTERED_DIR}')
        write_files = True
        if not os.path.exists(article_dir):
            os.makedirs(article_dir, exist_ok=False)
        elif update:
            logger.warning(f"Files for article {a_short_doi} and its sub-articles already exist in {FILTERED_DIR} and will be overwritten.")
        else:
            write_files = False
        logger.debug("Parsing sub-articles...")
        # iterate over sub-articles
        for sub_a in a.get_subarticles():
            sub_a_metadata = parse_subarticle(sub_a)
            if 'specific_use' in sub_a_metadata.keys():
                if sub_a_metadata['specific_use'] == 'acceptance-letter':
                    # skipping those to save space and time
                    continue
            subtree = et.ElementTree(sub_a)
            # find a warning (if any)
            boxed_text = subtree.find('.//boxed-text')
            if boxed_text is not None:
                logger.warning(f"{boxed_text.find('.//title').text.strip()} in {sub_a_metadata['doi']}:\n{boxed_text.find('.//p').text.strip()}")
            if write_files:
                if not os.path.exists(sub_articles_dir):
                    os.mkdir(sub_articles_dir)
                # download supplementary materials (if any)
                if not skip_sm_dl and 'supplementary_materials' in sub_a_metadata.keys():
                    for sm in sub_a_metadata['supplementary_materials']:
                        with open(os.path.join(sub_articles_dir, sm['filename']), 'wb') as fp:
                            url = 'https://doi.org/' + metadata['doi'] + get_extension_from_str(sm['id'])
                            logger.debug(f'Downloading supplementary material from {url}')
                            r = requests.get(url, stream=True)
                            fp.write(r.content)
                 # saving this sub-article:
                sub_a_filename = sub_a_metadata['id'] + '.xml'
                sub_a_path = os.path.join(sub_articles_dir, sub_a_filename)
                subtree.write(sub_a_path)
                sub_a_metadata['supplementary_materials'].append({
                    'filename': sub_a_filename, 'id': sub_a_metadata['id'], 'title': "This sub_article in XML."
                })
                # save metadata to JSON:
                with open(os.path.join(sub_articles_dir, sub_a_metadata['id'] + '.json'), 'w+') as fp:
                    json.dump(sub_a_metadata, fp)
                logger.debug(f"Sub-article {sub_a_metadata['doi']} saved to {FILTERED_DIR}{os.path.sep}{a_short_doi}")
            metadata['sub_articles'].append(sub_a_metadata)
            
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
        logger.debug(f"Metadata for {a_short_doi} saved to {ALL_ARTICLES_DIR}.")
    return metadata
    
    
def get_article_files(rescan_reviewed = False):
    """
    Generator for obtaining the relevant files from PLOS corpus, either in the zipped or unzipped form.

    :param rescan_reviewed: if set to `True`, then only articles that already have a directory in `FILTERED_DIR` will be processed

    :return: a tuple: `(filename, fp)` where `fp` is a readable filepointer to the file named `filename`.
    :rtype: tuple
    """
    if not os.path.exists(zipfile_path):
        logger.debug("Did not find the zip file containing the PLOS corpus, will try to look for the unzipped files in the default location.")
        from_zip = False
        if not os.path.isdir(default_extract_dir):
            logger.error("Unable to locate the PLOS corpus! Crawler will shut down.")
            return
        else:
            logger.info("PLOS corpus located in directory" + default_extract_dir)
    else:
        from_zip = True
        allofplos_zip = ZipFile(zipfile_path, 'r')
    if rescan_reviewed:
        reviewed = os.listdir(filtered_path)
        if from_zip:
            filenames = filter(lambda f: os.path.splitext(f)[0] in reviewed, allofplos_zip.namelist())
        else:
            filenames = filter(lambda f: os.path.splitext(f)[0] in reviewed, os.listdir(default_extract_dir))
    else:
        filenames = allofplos_zip.namelist()
    for filename in filenames:
        if from_zip:
            fp = allofplos_zip.open(filename)
        else:
            fp = open(os.path.join(input_path, filename), 'rb')  # using bytes because lxml.etree likes them better
        yield filename, fp


def process_allofplos_zip(update = False, rescan_reviewed = False, skip_sm_dl = False):
    """
    Goes through the zip file contents and extracts XML files for reviewed articles, as well as metadata.
    For each article in the zip, metadata is extracted and stored in a JSON file in `ALL_ARTICLES_DIR`. 
    These files will be overwritten if the flag `update` is set to `True`.
    
    The XML files and JSON files containing reviewed articles and their metadata are saved into subdirectories named after the article's DOI.
    Sub-articles (reviews, decision letters etc.) are saved to subdirectories named 'sub-articles'.
    
    :param update: if is set to `True`, already existing files will be overwritten. Otherwise (and by default), files that were already parsed are skipped.
    :param rescan_reviewed:  if set to `True`, then only articles that already have a directory in `FILTERED_DIR` will be processed
    :param skip_sm_dl: whether to skip downloading supplementary materials. 
    
    """

    logger.debug(f'Setting up a PLOScrawler to go through allofplos_xml.zip | update = {update}, rescan_reviewed = {rescan_reviewed}, skip_sm_dl = {skip_sm_dl}')

    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    reviewed_counter = 0
    errors_counter = 0 
    
    reviewed = os.listdir(filtered_path)

    for filename, fp in get_article_files(rescan_reviewed = rescan_reviewed):
        try:
            a_short_doi = os.path.splitext(filename)[0]     # TODO: find a better, universal way to get identifiers from filenames
            metadata_file_exists = os.path.exists(os.path.join(all_articles_path, a_short_doi +".json"))
            if metadata_file_exists and not update and not a_short_doi in reviewed:    # NOTE: reviewed articles are NEVER skipped
                logger.debug(f'Skipping {filename} as it was already parsed.')
                continue
            elif metadata_file_exists and update:
                logger.info(f"File with metadata for {a_short_doi} already exists in {ALL_ARTICLES_DIR} and will be overwritten.")
            logger.debug(f'Processing file {filename}')
            a_xml = fp.read()
            fp.close()

            a_metadata = parse_article_xml(a_xml, update = update, skip_sm_dl = skip_sm_dl)
            if a_metadata['has_reviews']: reviewed_counter += 1
            
        except Exception as e:
            errors_counter += 1
            logger.error(f"There was a {e.__class__.__name__} while parsing {filename} from zip: {str(e)}")
        
    logger.info(f"Finished parsing allofplos_xml.zip with {errors_counter} errors encountered in the meantime.")
    logger.info(f"Found {reviewed_counter} reviewed articles.")
    

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = "Find reviewed articles in the allofplos corpus.", epilog="Detects which articles had been peer-reviewed, extracts them from the zip into subdirectories in `plos/reviewed_articles`. Additionally, the sub-articles (reviews and such) from each xml are extracted and saved into files. Parsed metadata about each article in the zip file is saved to `plos/all_articles` directory")
    parser.add_argument('--download', action='store_true', help=
                        'Download the entire allofplos corpus zip file to the input dir before starting the crawler.', dest='download')
    parser.add_argument('--unzip', action='store_true', help=
                        'Unzip the allofplos corpus before starting the crawler. The zip archive will be removed after extracting the files.', dest='unzip')
    # parser.add_argument('--input-dir', action='store', help=
    #                     'Set the input dir', default=zipfile_dir)
    # TODO: add other arguments for the argparser: update, rescan etc. 
    
    args = parser.parse_args()
    
    if args.download:
        zip_path = download_corpus_zip(zipfile_dir)
    if args.unzip:
        unzip_articles(zip_path, extract_directory = default_extract_dir, delete_file = True)
    process_allofplos_zip(update = True, rescan_reviewed = False, skip_sm_dl = False)
