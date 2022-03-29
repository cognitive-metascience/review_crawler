
import json
import logging
import os
import random
import shutil
import time
import requests
# import jsonschema

from bs4 import BeautifulSoup
from typing import Union

# globals:

# Time Between Requests (in seconds):
MIN_TBR = 0.5
MAX_TBR = 4.5

proxies = {'https': "https://10.10.1.11:1080"}

# paths:
crawler_dir = os.path.dirname(__file__)
logs_path = os.path.join(crawler_dir, 'logs')
if not os.path.exists(logs_path):
    os.makedirs(logs_path)
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
    soup = BeautifulSoup(requests.get(url, proxies=proxies).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup

# def validate_json(json_data):
#     try:
#         jsonschema.validate(json_data, article_schema)
#     except jsonschema.ValidationError as err:
#         print(err.args[0])
#     else:
#         print("passed.")

def getLogger(logger_name, logs_path=logs_path) -> logging.Logger:
    runtime_dirname = '_'.join(time.ctime().split(' ')[1:3]).replace(':', '_')
    log_filename = runtime_dirname + ".log"
    
    _PARENT_LOGGER = logging.getLogger(logger_name)
    logger = _PARENT_LOGGER.getChild('file')
    logging_file_handler = logging.FileHandler(
        os.path.join(logs_path, log_filename))
    logging_file_handler.formatter = logging.Formatter(
        '%(asctime)s|%(module)s.%(funcName)s:%(lineno)d|%(levelname)s:%(message)s|', '%H:%M:%S')
    logger.addHandler(logging_file_handler)
    logging_stream_handler = logging.StreamHandler()
    logging_stream_handler.formatter = logging.Formatter(
        '|%(levelname)s:%(message)s|')
    _PARENT_LOGGER.setLevel(logging.WARNING)
    _PARENT_LOGGER.addHandler(logging_stream_handler)
    logger.setLevel(logging.DEBUG)
    return logger

def clean_log_folder(logs_path=logs_path):
    for path in os.listdir(logs_path):
        joined_paths = os.path.join(logs_path, path)
        if os.path.isdir(joined_paths) and len(os.listdir(joined_paths)) == 0:
            os.rmdir(joined_paths)
        if os.path.getsize(joined_paths) < 64:
            os.remove(joined_paths)
    if len(os.listdir(logs_path)) == 0:
        os.rmdir(logs_path)


def filter_articles(src, dest) -> None:
    for file in os.listdir(os.path.abspath(src)):
        filepath = os.path.join(os.path.abspath(src), file)
        if os.path.isdir(filepath):
            continue
        with open(filepath) as fp:
            article = json.load(fp)
            for key in article.keys():
                print(f"{key}: {article[key]}")
            if article["has_reviews"]:
                shutil.move(filepath, dest)


# if __name__ == "__main__":
    # articles_dir = "./mdpi/scraped/articles"
    # output_dir = "./mdpi/scraped/filtered"
    # filter_articles(articles_dir, output_dir)