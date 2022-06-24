Uses the __allofplos__ Python package (https://doi.org/10.25080/Majora-4af1f417-009) to parse and extract metadata from articles in PLOS database.

## Installation

After cloning the parent repository, change working directory to this folder:

`>` ```cd review_crawler/```

Install required Python packages:

`>` ```pip install -r requirements.txt```

Clone the `allofplos` fork:

`>` ```git sumbodule update --init```

## Usage

Before running, make sure your current working directory is set to `review_crawler`, like above. 
Scripts `plos_crawler.py` and `mdpi_crawler.py` can be run from the command line like this:

`>` ```python plos_crawler.py```
