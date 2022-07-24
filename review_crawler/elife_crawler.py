import json
import os
import requests
import lxml.etree as et

from rarticle import Article
from utils import get_logger, get_extension_from_str, CRAWLER_DIR, OUTPUT_DIR

# globals:

# these paths are relative to `CRAWLER_DIR` which should be where this script is located
ELIFE_CORPUS_DIR = os.path.join("elife-article-xml", "articles")
elife_corpus_path = os.path.join(CRAWLER_DIR, ELIFE_CORPUS_DIR)

# this is where parsed data is stored:
ALL_ARTICLES_DIR = os.path.join("elife", "all_articles" )
FILTERED_DIR = os.path.join("elife", "reviewed_articles")
all_articles_path = os.path.join(OUTPUT_DIR, ALL_ARTICLES_DIR)
filtered_path = os.path.join(OUTPUT_DIR, FILTERED_DIR)


# logging:
logs_path = os.path.join(CRAWLER_DIR, 'logs')
json_logfile = os.path.join(logs_path, 'elife_lastrun.json')
logger = get_logger("plosLogger", logs_path)


# transformations:

def filename_to_short_doi(filename: str) -> str:
    return filename.replace('-', '.', 1).split('-')[0]

def doi_to_short_doi(doi: str) -> str:
    return doi.split('/')[-1]

def doi_to_url(doi: str) -> str:
    return "https://elifesciences.org/articles/" + doi.split('.')[-1]


def parse_subarticle(root: et.Element) -> dict:
    metadata = {}
    front = root.find('front-stub')
    body = root.find('body')

    metadata['type'] = root.attrib['article-type']
    metadata['doi'] = front.find('article-id').text.strip()
    # here ends super code
    orig_doi = metadata['doi'].rsplit('.', 1)[0]
    metadata['original_article_doi'] = orig_doi
    
    # in addition to a doi, elife articles have an 'id' (root.attrib['id'])
    # however, we have our own standard for creating ids
    if metadata['type'] == 'reply':
        id_str = doi_to_short_doi(orig_doi)+".a{}"
    else:
        id_str = doi_to_short_doi(orig_doi)+".r{}"
    metadata['id'] = id_str.format( get_extension_from_str(metadata['doi'])[1:])
    
    # TODO: parse rounds: in eLife they are containd within the same sub-article
    
    metadata['reviewers'] = []
    for contrib in front.findall('.//contrib'):
        if contrib.attrib['contrib-type'] == "reviewer":
            metadata['reviewers'].append({
                'name': f"{contrib.find('.//given-names').text.strip()} {contrib.find('.//surname').text.strip()}"
            })
        else:
            metadata[contrib.attrib['contrib-type']] = {
                'name': f"{contrib.find('.//given-names').text.strip()} {contrib.find('.//surname').text.strip()}"
            }
    # TODO: find out reviewer numbers and how many reviewers were anonymous
    

    # TODO: find supplementary materials (if any):
    supplementary = []
    for elem in body.findall('supplementary-material'):
        sm = {'id': ('journal.'+elem.attrib['id']), # these will be in "short" doi format
              'original_filename': elem.find('.//named-content').text}
        sm['filename'] = sm['id'] + get_extension_from_str(sm['original_filename'])
        supplementary.append(sm)
    metadata['supplementary_materials'] = supplementary

    return metadata


def parse_article_xml(xml_string: str, update = False, skip_sm_dl = False) -> dict:
    """
    Parses an XML string that's assumed to contain a research article.
    This function relies on the `Article` class (originally from `allofplos` library) to extract metadata from XML.
    
    JSON files containing parsed metadata are stored in `ALL_ARTICLES_DIR`.
    Files containing reviewed articles, their sub-articles and supplementary materials are saved to sub-directories in `FILTERED_DIR`. 
    Metadata in JSON format is also saved there. 

    :param xml_string: XML-encoded string containing a research article.
    :param update: if set to `True`, existing files will be overwritten.
    :param skip_sm_dl: whether to skip downloading supplementary materials.
    :return: dictionary object containing parsed metadata
    :rtype: dict
    """
    a = Article.from_xml(xml_string)
    a_short_doi = doi_to_short_doi(a.doi)
    metadata = {}
    # get metadata from Article object:
    metadata['doi'] = a.doi
    metadata['title'] = a.title
    metadata['url'] = doi_to_url(a.doi)
    # metadata['fulltext_pdf_url'] =  TODO: some kind of link is available in the XML, but it's relative and I don't the base form
    metadata['journal'] = {'title': a.journal, 'volume': a.volume}  # elife journals don't have issues
    metadata['publication_date'] = {'year': a.pubdate.year,
                                    'month': a.pubdate.month, 
                                    'day': a.pubdate.day}
    metadata['authors'] = a.get_author_names()
    metadata['keywords'] = a.keywords
    metadata['retracted'] = False # TODO: change to check_if_article_retracted
    
    # assuming if sub-articles are present, then article was reviewed
    if len(a.get_subarticles()) > 0:
        metadata["has_reviews"] = True
        # TODO: provide a link to reviews!
        metadata['sub_articles'] = []
        
        article_dir = os.path.join(filtered_path, a_short_doi)
        sub_articles_dir = os.path.join(article_dir, "sub-articles")
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
            sub_a_metadata = parse_subarticle(sub_a)
            # find a warning (if any)
            # boxed_text = subtree.find('.//boxed-text')
            # if boxed_text is not None:
            #     logger.warning(f"found boxed_text in {sub_a_metadata['doi']}:\n{boxed_text.find('.//p').text.strip()}")
            if write_files:
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
                if not os.path.exists(sub_articles_dir):
                    os.mkdir(sub_articles_dir)
                subtree.write(sub_a_path)
                sub_a_metadata['supplementary_materials'].append({
                    'filename': sub_a_filename, 'id': sub_a_metadata['id'], 'title': "This sub_article in XML."
                })
                # save metadata to JSON:
                with open(os.path.join(sub_articles_dir, sub_a_metadata['id'] + '.json'), 'w+') as fp:
                    json.dump(sub_a_metadata, fp)
                logger.debug(f"sub-article {sub_a_metadata['doi']} saved to {FILTERED_DIR}{os.path.sep}{a_short_doi}")
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
        logger.debug(f"metadata for {a_short_doi} saved to {ALL_ARTICLES_DIR}.")
    return metadata


def get_article_files():
    """
    Generator for obtaining the relevant files from eLife corpus: gets only the file with the newest version of a given article.

    Yields:
        tuple: a tuple: `(filename, fp)` where `fp` is a readable filepointer to the file named `filename` located within `elife_corpus_path`.
    """
    articles = {}
    for filename in os.listdir(elife_corpus_path):
        filen = os.path.splitext(filename)
        # ignore everything that is not an XML
        if filen[1].lower() != '.xml':
            continue
        try:
            splat = filen[0].split('-v')
            v_no = int(splat[-1])
            if splat[0] in articles:
                if v_no < articles[splat[0]][0]:
                    continue
            articles[splat[0]] = v_no, filename
        except Exception as e:
            logger.info(f"Surprising filename found: {filename}|Exception caught: {e}")
            articles[filename] = -1, filename
        
    for a in articles:
        v_no, filename = articles[a]
        fp = open(os.path.join(elife_corpus_path, filename), 'rb')  # using bytes because lxml.etree likes them better
        yield filename, fp
        

def process_article(a_filename, update = False, skip_sm_dl = False):
    logger.info(f'Processing {a_filename}')
    with open(os.path.join(elife_corpus_path, a_filename), 'rb') as fp:
        a_xml = fp.read()
    return  parse_article_xml(a_xml, update = update, skip_sm_dl = skip_sm_dl)
    

def process_elife_corpus(update = False, skip_sm_dl = False):
    """
    Goes through the eLife corpus, parses metadata from each article.
    For each article in the zip, metadata is extracted and stored in a JSON file in `ALL_ARTICLES_DIR`. 
    These files will be overwritten if the flag `update` is set to `True`.
    
    The XML files and JSON files containing reviewed articles and their metadata are saved into subdirectories named after the article's DOI.
    Sub-articles (reviews, decision letters etc.) are saved to subdirectories named 'sub-articles'.
    
    :param update: if is set to `True`, already existing files will be overwritten. Otherwise (and by default), files that were already parsed are skipped.
    :param skip_sm_dl: whether to skip downloading supplementary materials. 
    
    """

    logger.debug(f'setting up a crawler to go through eLife corpus. | update = {update} ')
    if not os.path.exists(filtered_path):
            os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    reviewed_counter = 0
    errors_counter = 0 
    
    for filename, fp in get_article_files():
        try:
            a_short_doi = filename_to_short_doi(filename)     # TODO: find a better, universal way to get identifiers from filenames
            metadata_file_exists = os.path.exists(os.path.join(all_articles_path, a_short_doi +".json"))
            # skipping files that were already parsed:
            if metadata_file_exists and not update and not a_short_doi in os.listdir(filtered_path):    # NOTE: reviewed articles are NEVER skipped
                logger.debug(f'Skipping {filename} as it was already parsed.')
                continue
            elif metadata_file_exists and update: 
                logger.warning(f"file with metadata for {a_short_doi} already exists in {ALL_ARTICLES_DIR} and will be overwritten.")
                
            logger.info(f'Processing {filename}')
            a_xml = fp.read()
            fp.close()
            
            a_metadata = parse_article_xml(a_xml, update = update, skip_sm_dl = skip_sm_dl)
            if a_metadata['has_reviews']: reviewed_counter += 1
            
        except Exception as e:
            errors_counter += 1
            logger.error(f"There was a {e.__class__.__name__} while parsing {filename}: {str(e)}")
        
    logger.info(f"Finished parsing the eLife corpus with {errors_counter} errors encountered in the meantime.")
    logger.info(f"found {reviewed_counter} reviewed articles.")
    

if __name__ == '__main__':
    logger.parent.handlers[0].setLevel("INFO")
    process_article('elife-47612-v2.xml', True, False)
    # process_elife_corpus(update = True)