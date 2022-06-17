
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
from typing import Union

# globals:

# Time Between Requests (in seconds):
MIN_TBR = 0.5
MAX_TBR = 4.5

# directories:
crawler_dir = os.path.dirname(__file__)
logsdir_path = os.path.join(crawler_dir, 'logs')
if not os.path.exists(logsdir_path):
    os.makedirs(logsdir_path)

# this is time (month and day) as of starting a crawler
start_monthday = '_'.join(time.ctime().split(' ')[1:3]).replace(':', '_')
log_default_filename = start_monthday + ".log"    # e.g. Apr_1.log


# _article_schema_path = os.path.join(crawler_dir, "article_schema.json")
# fp = open(_article_schema_path, 'r')
# article_schema = json.loads(fp.read())
# fp.close()

# example_article_path = os.path.join(crawler_dir, "example_article.json")

def cook(url: str) -> Union[BeautifulSoup, None]:
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
    if '.' in text:
        return '.' + text.split('.')[-1]
    else: return text


# def validate_json(json_data):
#     try:
#         jsonschema.validate(json_data, article_schema)
#     except jsonschema.ValidationError as err:
#         print(err.args[0])
#     else:
#         print("passed.")

def get_logger(logger_name: str, logs_path=logsdir_path, log_filename = log_default_filename,
            fileh_level=logging.DEBUG, streamh_level=logging.WARNING) -> logging.Logger:
    
    file_handler = logging.FileHandler(os.path.join(logs_path, log_filename))
    file_handler.formatter = logging.Formatter(
        '%(asctime)s|%(module)s.%(funcName)s:%(lineno)d|%(levelname)s:%(message)s|', '%H:%M:%S')
    file_handler.setLevel(fileh_level)

    stream_handler = logging.StreamHandler(stream = sys.stdout)
    stream_handler.formatter = logging.Formatter('|%(levelname)s:%(message)s|')
    stream_handler.setLevel(streamh_level)

    _parent_logger = logging.getLogger(logger_name)
    _logger = _parent_logger.getChild('file')
    
    _parent_logger.propagate = False
    _logger.propagate = True

    _parent_logger.setLevel(streamh_level)
    _logger.setLevel(fileh_level)

    _logger.addHandler(file_handler)
    _parent_logger.addHandler(stream_handler)

    return _logger

def clean_log_folder(logs_path=logsdir_path):
    for path in os.listdir(logs_path):
        joined_paths = os.path.join(logs_path, path)
        if os.path.isdir(joined_paths) and len(os.listdir(joined_paths)) == 0:
            os.rmdir(joined_paths)
        if os.path.getsize(joined_paths) < 64:
            os.remove(joined_paths)
    if len(os.listdir(logs_path)) == 0:
        os.rmdir(logs_path)


def filter_articles(src, dest) -> None:
    """
    Given two directories: src and dest, will try to read JSON files from src, and move them to dest if they contain property 'has_reviews' and it's set to True

    """
    if not os.path.exists(dest):
        os.makedirs(dest)
    
    for file in os.listdir(os.path.abspath(src)):
        filepath = os.path.join(os.path.abspath(src), file)
        if os.path.isdir(filepath):
            continue
        with open(filepath) as fp:
            try:
                article = json.load(fp)
                if 'has_reviews' not in article or not isinstance(article["has_reviews"], bool):
                    logging.info(f"{file} does not match the expected JSON format for articles: Does not have 'has_reviews' as a property.")
                    continue
                if article["has_reviews"]:
                    if os.path.exists(os.path.join(dest, file)):
                        logging.info(f"{file} already in {dest}. Will NOT overwrite.")
                    else:
                        logging.debug(f"Moving {file} to {dest}")    
                        shutil.move(filepath, dest)
            except UnicodeDecodeError as e:
                logging.info(f"{file} does not contain valid Unicode data.\nFull traceback:{e}")
            except json.JSONDecodeError as e:
                logging.info(f"{file} does not contain valid JSON data.\nFull traceback:{e.msg}")


if __name__ == "__main__":
    articles_dir, output_dir =  "./mdpi/scraped/sample", "./mdpi/scraped/filtered"
    filter_articles(articles_dir, output_dir)