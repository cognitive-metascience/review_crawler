Uses the __allofplos__ Python package (https://doi.org/10.25080/Majora-4af1f417-009) to parse and extract metadata from articles in PLOS database.

## Installation

After cloning the parent repository, change working directory to this folder:

`>` ```cd review_crawler/```

Install required Python packages:

`>` ```pip install -r requirements.txt```

The following command clones the __allofplos__ fork, which is necessary to run `plos_crawler`, and also downloads the entire eLife corpus from the __elife-article-xml__ repo (be warned: this corpus contains nearly 3 GB of data!):

`>` ```git sumbodule update --init```

## Usage

Before running, make sure your current working directory is set to `review_crawler`, like above. 
Scripts `plos_crawler.py` and `mdpi_crawler.py` can be ran from the command line like this:

`>` ```python plos_crawler.py```
