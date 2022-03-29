
"""test crawler for going through the PLOS website and the "allofplos_xml.zip" file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into filtered_path
Additionally, the sub-articles from each xml are extracted and saved into files in all_articles_path
"""

import json
import logging
import os
import zipfile
import xml.etree.cElementTree as ET
import allofplos

from utils import cook, getLogger

# globals:
crawler_dir = os.path.abspath(os.path.dirname(__file__))

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
json_logfile = os.path.join(logs_path, 'plos_lastrun.json')
logger = getLogger("plosLogger", logs_path)


def _shorten(url):
    if 'plos.org/' in url and 'article' in url: return (url.split('/')[-1])
    else: return url


def get_metadata_from_url(url, dump_dir=None):
    """
    Parses a PLOS article with the given url. Saves output to a JSON file if dump_dir is specified.

    :type dump_dir: str
    :type url: str
    :return: dict containing scraped metadata
    :rtype: dict
    """

    if not 'plos.org/' in url:
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


def get_metadata_from_xml(root: str) -> dict:
    metadata = {}
    metadata['title'] = root.find('.//title-group').find('article-title').text
    el: ET.Element
    for el in root.iter('article-id'):
        metadata[el.attrib['pub-id-type']] = el.text    # this is wrong. todo: fix
    return metadata


def process_allofplos_zip(save_all_metadata = True, print_logs=False):
    if print_logs:
        logger.setLevel(logging.INFO)
        logger.parent.handlers[0].setLevel(logging.DEBUG)

    logger.debug(f"crawler_dir: {crawler_dir}")

    zipfile_path = os.path.join(crawler_dir, 'allofplos_xml.zip')
        
        # //allofplos
    filtered_path = os.path.join(crawler_dir, 'plos/scraped_from_zip/reviewed_articles')
    all_articles_path = os.path.join(crawler_dir, 'plos/scraped_from_zip/all_articles')

    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(all_articles_path):
        os.makedirs(all_articles_path)

    # check how many files were done during last run:
    done_files = 0
    if os.path.exists(json_logfile) and os.path.getsize(json_logfile) > 1:
        with open(json_logfile, 'r') as fp:
            lastrun_data = json.load(fp)
            if 'done_files' in lastrun_data.keys():
                done_files = lastrun_data['done_files']

    try:
        with zipfile.ZipFile(zipfile_path, 'r') as zip:
            for filename in zip.namelist()[done_files:]:
                logger.info(f'Processing {filename}')
                fp = zip.open(filename)
                root = ET.parse(fp)
                fp.close()
                metadata = get_metadata_from_xml(root)

                # checking for reviews:
                sub_articles = root.findall('sub-article')
                # assuming if sub-articles are present, then there are reviews
                if len(sub_articles) > 0:
                    metadata["has_reviews"] = True
                    article_dir = os.path.join(filtered_path, os.path.splitext(filename)[0])
                    if os.path.exists(article_dir):
                        logger.info('We already have this article in reviewed_articles.')
                    else:
                        logging.info('This article probably has reviews. Saving it to reviewed_articles.')
                        os.mkdir(article_dir)
                        root.write(os.path.join(article_dir, filename))
                        with open(os.path.join(article_dir, "metadata.json"), 'w+') as fp:
                            json.dump(metadata, fp)
                    for sub_a in sub_articles:
                        logger.debug(f"sub-article: {sub_a.attrib}")
                        subtree = ET.ElementTree(sub_a)
                        doi = subtree.find('.//article-id').text
                        path = os.path.join(article_dir, "sub-articles", doi.split('/')[-1]+'.xml')
                        if not os.path.exists(os.path.join(article_dir, "sub-articles")):
                            os.mkdir(os.path.join(article_dir, "sub-articles"))
                        if not os.path.exists(path):
                            subtree.write(path)
                
                # finally, save metadata to all_articles
                if save_all_metadata and not os.path.exists(os.path.join(all_articles_path, os.path.splitext(filename)[0]+".json")):
                    with open(os.path.join(all_articles_path, os.path.splitext(filename)[0]+".json"), 'w+') as fp:
                        json.dump(metadata, fp)
                done_files += 1

            lastrun_data['done_files'] = done_files
    except FileNotFoundError:
        logger.error("allofplos_xml.zip not found in crawler_dir")
        exit()
    except KeyboardInterrupt:
        with open(json_logfile, 'w+') as fp:
            json.dump(lastrun_data, fp)
    else:
        with open(json_logfile, 'w+') as fp:
            json.dump(lastrun_data, fp)


if __name__ == '__main__':
    process_allofplos_zip(save_all_metadata = False,
                            print_logs = True)
