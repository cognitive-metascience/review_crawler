
import json
import logging
import os
import random
import shutil
import sys
import time
import requests
# import jsonschema

from bs4 import BeautifulSoup

# globals:
# Time Between Requests (in seconds):
MIN_TBR = 0.5
MAX_TBR = 4.5


# directories:
CRAWLER_DIR = os.path.abspath(os.path.dirname(__file__))
OUTPUT_DIR = os.path.join(CRAWLER_DIR, "output")
INPUT_DIR = os.path.join(CRAWLER_DIR, "input")

LOGS_DIR = os.path.join(CRAWLER_DIR, "logs")
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# this is time as of starting a crawler
start_monthday = '_'.join(time.ctime().split(' ')[1:4]).replace(':', '_')
log_default_filename = f"{start_monthday}_.log"    # e.g. Apr_1_20_12_42.log


# _article_schema_path = os.path.join(CRAWLER_DIR, "article_schema.json")
# fp = open(_article_schema_path, 'r')
# article_schema = json.loads(fp.read())
# fp.close()

# example_article_path = os.path.join(CRAWLER_DIR, "example_article.json")

def cook(url: str) -> BeautifulSoup | None:
    # sleep for some time before a request
    sleepytime = random.random()*(MAX_TBR - MIN_TBR)+MIN_TBR
    logging.debug("cook: Sleeping for "+str(sleepytime)+" seconds...")
    time.sleep(sleepytime)
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup

def cook_from_html(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, 'lxml')

def get_extension_from_str(text) -> str:
    return os.path.splitext(text)[-1]


# def validate_json(json_data):
#     try:
#         jsonschema.validate(json_data, article_schema)
#     except jsonschema.ValidationError as err:
#         print(err.args[0])
#     else:
#         print("passed.")


def get_logger(logger_name: str, logs_path=LOGS_DIR, log_filename = log_default_filename,
            fileh_level=logging.DEBUG, streamh_level=logging.WARNING) -> logging.Logger:
    
    file_handler = logging.FileHandler(os.path.join(logs_path, logger_name+'_'+log_filename))
    file_handler.formatter = logging.Formatter(
        '%(asctime)s|%(funcName)s:%(lineno)d|%(levelname)s:%(message)s|', '%H:%M:%S')
    file_handler.setLevel(fileh_level)

    stream_handler = logging.StreamHandler(stream = sys.stdout)
    stream_handler.formatter = logging.Formatter('|%(levelname)s:%(message)s|')
    stream_handler.setLevel(streamh_level)

    _parent_logger = logging.getLogger(__name__).getChild(logger_name)
    _logger = _parent_logger.getChild('file')
    
    _parent_logger.propagate = False
    _logger.propagate = True

    _parent_logger.setLevel(streamh_level)
    _logger.setLevel(fileh_level)

    _logger.addHandler(file_handler)
    _parent_logger.addHandler(stream_handler)

    return _logger


def clean_log_folder(logs_path=LOGS_DIR):
    for path in os.listdir(logs_path):
        joined_paths = os.path.join(logs_path, path)
        if os.path.isdir(joined_paths) and len(os.listdir(joined_paths)) == 0:
            os.rmdir(joined_paths)
        if os.path.getsize(joined_paths) < 64:
            os.remove(joined_paths)
    if len(os.listdir(logs_path)) == 0:
        os.rmdir(logs_path)


def filter_articles(src, dest, key, 
                    scan_subdirs = True, update = False) -> None:
    """
    Given two directories: src and dest, will try to read JSON files from src, and move them to dest if they contain property `key` and it's set to True
    The parameter scan_subdirs sets whether the search will go one lever deeper in search for JSON files.
    """
    if not os.path.exists(dest):
        os.makedirs(dest)
    
    
    if scan_subdirs:
        json_files = []
        for dir in [p for p in os.listdir(src) if os.path.isdir(os.path.join(src, p))]:
            json_files += [(dir, f) for f in os.listdir(
                os.path.abspath(os.path.join(src, dir))) if f.lower().endswith('.json')]
    else:        
        json_files = [(src, f) for f in os.listdir(os.path.abspath(src)) if f.lower().endswith('.json')]
    logging.info(f"Loaded {len(json_files)} JSON files.")
    for dir, file in json_files:
        if scan_subdirs:
            filepath = os.path.join(os.path.abspath(src), dir, file)
        else:
            filepath = os.path.join(os.path.abspath(src), file)
        if os.path.isdir(filepath):
            continue
        fp = open(filepath, 'r', encoding='utf-8')
        try:
            article = json.load(fp)
            fp.close()
            if key not in article:
                logging.info(f"{dir}/{file} does not match the expected JSON format: Does not contain the property '{key}'.")
                continue
            if not isinstance(article[key], bool):
                logging.info(f"{dir}/{file} does not match the expected JSON format: '{key}' is not a bool!")
                continue
            v = article.get(key)
            if v is None:
                logging.info(f"{dir}/{file} does not match the expected JSON format: '{key}' is None!")
                continue
            if scan_subdirs:
                if os.path.exists(os.path.join(dest, dir)) and not update:
                    logging.info(f"{dir} already in {dest}. Will NOT overwrite.")
                else:
                    logging.debug(f"Moving {dir} to {dest}")    
                    shutil.move(os.path.join(src, dir), dest)
            else:
                if os.path.exists(os.path.join(dest, file)) and not update:
                    logging.info(f"{file} already in {dest}. Will NOT overwrite.")
                else:
                    logging.debug(f"Moving {file} to {dest}")    
                    shutil.move(filepath, dest)
        except UnicodeDecodeError as e:
            logging.error(f"{dir}/{file} does not contain valid Unicode data.\nFull traceback:{e}")
        except json.JSONDecodeError as e:
            logging.error(f"{dir}/{file} does not contain valid JSON data.\nFull traceback:{e.msg}")
        except PermissionError as e:
            logging.error(f"PermissionError while moving {dir}/{file}:\n{e.msg}")
            
