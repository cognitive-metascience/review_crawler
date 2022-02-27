
"""test crawler for going through the PLOS website and the "allofplos_xml.zip" file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into filtered_dirname
Additionally, the sub-articles from each xml are extracted and saved into files in subarticles_dirname
"""

import json
import logging
import os
import time
import zipfile
import xml.etree.cElementTree as ET

from varyous import _cook


# for logging:
logs_path = os.path.join(os.path.dirname(__file__), 'logs')
runtime_dirname = '_'.join(time.ctime().split(' ')[1:4]).replace(':', '_')
log_filename = runtime_dirname + ".log"
if not os.path.exists(logs_path):
    os.makedirs(logs_path)
LOGGER = logging.getLogger("mdpiLogger")
logger = LOGGER.getChild('stream')
logging_file_handler = logging.FileHandler(os.path.join(logs_path, log_filename))
logging_file_handler.formatter = logging.Formatter('%(asctime)s|%(module)s.%(funcName)s:%(lineno)d|%(levelname)s:%(message)s|', '%H:%M:%S')
logger.addHandler(logging_file_handler)
logging_stream_handler = logging.StreamHandler()
logging_stream_handler.setLevel(logging.WARNING)
logging_stream_handler.formatter = logging.Formatter('|%(levelname)s:%(message)s|')
LOGGER.setLevel(logging.WARNING)
LOGGER.addHandler(logging_stream_handler)
logger.setLevel(logging.DEBUG)


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
        soup = _cook(url)

    except Exception as e:
        logger.warning(f"There was a problem parsing article from {_shorten(url)}: {e}\narticle metadata: {metadata}")
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

if __name__ == '__main__':
    zipfile_path = os.path.join(os.path.dirname(__file__), 'allofplos_xml.zip')
    filtered_dirname =    os.path.join(os.path.dirname(__file__), 'plos/filtered_articles')
    subarticles_dirname = os.path.join(os.path.dirname(__file__), 'plos/scraped/sub-articles')
    if not os.path.exists(filtered_dirname):
        os.makedirs(filtered_dirname)
    if not os.path.exists(subarticles_dirname):
        os.makedirs(subarticles_dirname)
    
    logs_path = os.path.join(os.path.dirname(__file__), 'logs')
    logfile = os.path.join(logs_path, 'plos_lastrun.json')
    done_files = 0
    if os.path.exists(logfile) and os.path.getsize(logfile)>1:
        with open(logfile, 'r') as fp:
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
                print(f'Processing {metadata["doi"]}: {metadata["title"]}')
                
                # assuming if sub-articles are present, then there are reviews
                sub_articles = root.findall('sub-article')
                for sub_a in sub_articles:
                    print(f"sub-article: {sub_a.attrib}")
                    subtree = ET.ElementTree(sub_a)
                    doi = subtree.find('.//article-id').text
                    path = os.path.join(subarticles_dirname,doi.split('/')[-1]+'.xml')
                    if not os.path.exists(path):
                        subtree.write(path)
                if len(sub_articles) > 0:
                    if os.path.exists(os.path.join(filtered_dirname,filename)):
                        print('This article was already filtered.')
                    else:
                        print('This article probably has reviews. Moving it to filtered_dirname.')
                        root.write(os.path.join(filtered_dirname,filename))
                done_files+=1
    except KeyboardInterrupt:
        with open(logfile, 'w+') as fp:
            json.dump({'done_files':done_files}, fp)    
    else:
        with open(logfile, 'w+') as fp:
            json.dump({'done_files':done_files}, fp)    