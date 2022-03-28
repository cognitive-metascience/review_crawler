
import json
import logging
import os
import shutil
import time
import requests
from bs4 import BeautifulSoup
from typing import Union

logs_path = os.path.join(__file__, 'logs')

def cook(url: str) -> Union[BeautifulSoup, None]:
    soup = BeautifulSoup(requests.get(url).content, 'lxml')
    if "403 Forbidden" in soup.getText():
        raise Exception(f"403: I was forbidden access to this page: {url} ")
    return soup


def getLogger(logger_name, logs_path=logs_path) -> logging.Logger:
    runtime_dirname = '_'.join(time.ctime().split(' ')[1:3]).replace(':', '_')
    log_filename = runtime_dirname + ".log"
    if not os.path.exists(logs_path):
        os.makedirs(logs_path)
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

def clean_log_folder(logs_path):
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
        with open(filepath) as fp:
            article = json.load(fp)
            for key in article.keys():
                print(f"{key}: {article[key]}")
            if article["has_reviews"]:
                shutil.move(filepath, dest)


if __name__ == "__main__":
    articles_dir = "./mdpi/scraped/articles"
    output_dir = "./mdpi/scraped/filtered"
    filter_articles(articles_dir, output_dir)
