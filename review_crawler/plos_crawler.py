
"""test crawler for going through the PLOS website and the "allofplos_xml.zip" file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into filtered_path
Additionally, the sub-articles from each xml are extracted and saved into files in subarticles_path
"""

import json
import logging
import os
import zipfile
import xml.etree.cElementTree as ET
import allofplos

from utils import cook, getLogger

# globals:
crawler_dir = os.path.dirname(__file__)

# for logging:
logs_path = os.path.join(crawler_dir, 'logs')
json_logfile = os.path.join(logs_path, 'plos_lastrun.json')
logger = getLogger("plosLogger", logs_path)

def _shorten(url):
    if 'plos.org/' in url and 'article' in url: return (url.split('/')[-1])
    else: return url


def parse_article(url, dump_dir=None):
    """
    Parses a PLOS article with the given url. Saves output to a JSON file if dump_dir is specified.

    :type dump_dir: str
    :type url: str
    :return: dict containing scraped metadata
    :rtype: dict
    """

    if not url.contains("plos.org/"):
        raise Exception("Invalid url for parse_article.")

    metadata = {}
    logger.info(f"Parsing: {url}.")

    try:
        soup = cook(url)
        
        raise NotImplementedError()

    except Exception as e:
        logger.warning(f"There was a problem parsing article from {_shorten(url)}: {e}\narticle metadata: {metadata}")  # change?
        raise e

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
                logger.exception(f"Problem while saving to file: {filename}.\n{e}")
            else:
                logger.info(f"Saved metadata to file.")
    return metadata

def main():

    logger.debug(f"crawler_dir: {crawler_dir}")

    try:
        zipfile_path = os.path.join(crawler_dir, 'allofplos_xml.zip')
    except FileNotFoundError:
        # //allofplos
        logger.info("allofplos_xml.zip not found in crawler_dir")
    filtered_path =    os.path.join(crawler_dir, 'plos/scraped/filtered_articles')
    subarticles_path = os.path.join(crawler_dir, 'plos/scraped/sub-articles')
    


    if not os.path.exists(filtered_path):
        os.makedirs(filtered_path)
    if not os.path.exists(subarticles_path):
        os.makedirs(subarticles_path)    
    
    # check how many files were done during last run:
    done_files = 0
    if os.path.exists(json_logfile) and os.path.getsize(json_logfile)>1:
        with open(json_logfile, 'r') as fp:
            lastrun_data = json.load(fp)
            if 'done_files' in lastrun_data.keys():
                done_files = lastrun_data['done_files']
    
    try:
        with zipfile.ZipFile(zipfile_path, 'r') as zip:
            for filename in zip.namelist()[done_files:]:
                root = ET.parse(zip.open(filename)) 
                
                metadata = {}
                metadata['title'] = root.find('.//title-group').find('article-title').text
                el: ET.Element
                for el in root.iter('article-id'):
                    metadata[el.attrib['pub-id-type']] = el.text
                logger.info(f'Processing {metadata["doi"]}: {metadata["title"][:4]}')
                
                # assuming if sub-articles are present, then there are reviews
                sub_articles = root.findall('sub-article')
                for sub_a in sub_articles:
                    logger.debug(f"sub-article: {sub_a.attrib}")
                    subtree = ET.ElementTree(sub_a)
                    doi = subtree.find('.//article-id').text
                    path = os.path.join(subarticles_path,doi.split('/')[-1]+'.xml')
                    if not os.path.exists(path):
                        subtree.write(path)
                if len(sub_articles) > 0:
                    if os.path.exists(os.path.join(filtered_path,filename)):
                        logger.info('This article was already filtered.')
                    else:
                        logging.info('This article probably has reviews. Moving it to filtered_path.')
                        root.write(os.path.join(filtered_path,filename))
                done_files+=1
    except KeyboardInterrupt:
        with open(json_logfile, 'w+') as fp:
            json.dump({'done_files':done_files}, fp)    
    else:
        with open(json_logfile, 'w+') as fp:
            json.dump({'done_files':done_files}, fp)    

if __name__ == '__main__':
    main()