"""crawler for going through the `allofplos_xml.zip` file or unzipped directory.
Tries its best to detect which articles had been peer-reviewed.
For reviewed articles, it extracts ONLY the sub-articles (reviews, decisions, etc.)
into a single aggregated XML file saved to `plos/reviewed_articles/<DOI>/<short_doi>.xml`.
Parsed metadata about each article processed is saved to `plos/all_articles`.
Retraction status is determined using 'retraction_watch.csv' with auto-update on run.
"""

import argparse
import json
import os
import re
import requests
import lxml.etree as et
from zipfile import ZipFile
import time
import copy
import multiprocessing
from functools import partial
import csv

# Adjusted and updated imports for the installed allofplos package
try:
    from allofplos.article import Article
    from allofplos.corpus.plos_corpus import download_corpus_zip, unzip_articles
    from allofplos.plos_regex import validate_doi
except ImportError as e:
    print(f"Error importing base 'allofplos' components: {e}")
    print("Please ensure 'allofplos' library is correctly installed.")
    exit(1)

try:
    # Attempt to import validate_plos_url, provides fallback functions if missing
    from allofplos.plos_regex import validate_plos_url
except ImportError:
    print("Warning: 'validate_plos_url' not found in 'allofplos.plos_regex'. Using basic fallback validation.")
    def validate_plos_url(url: str) -> bool:
        """Basic fallback validation for PLOS URLs."""
        if not isinstance(url, str):
            return False
        return url.startswith("https://journals.plos.org/") or \
               url.startswith("https://doi.org/10.1371/") or \
               '?id=10.1371/' in url

try:
    from utils import get_extension_from_str, get_logger, OUTPUT_DIR, INPUT_DIR
except ImportError as e:
    print(f"Error importing from 'utils.py': {e}")
    print("Please ensure 'utils.py' is in the same directory or Python path.")
    exit(1)
except NameError as e_name:
     print(f"Note: Name error during utils import (likely 'cook' not found/needed): {e_name}")

# ===============================================
# Path Setup & Initialisation
# ===============================================
zipfile_dir = INPUT_DIR
zipfile_path = os.path.join(INPUT_DIR, 'allofplos.zip')
default_extract_dir = os.path.join(INPUT_DIR, 'allofplos_xml')

ALL_ARTICLES_DIR = os.path.join('plos', 'all_articles')
FILTERED_DIR = os.path.join('plos', 'reviewed_articles')
all_articles_path = os.path.join(OUTPUT_DIR, ALL_ARTICLES_DIR)
filtered_path = os.path.join(OUTPUT_DIR, FILTERED_DIR)

try:
    os.makedirs(all_articles_path, exist_ok=True)
    os.makedirs(filtered_path, exist_ok=True)
except OSError as e:
    print(f"CRITICAL ERROR: Could not create output directories: {e}. Exiting.")
    exit(1)

logger = get_logger("plos_parallel_autocsv", fileh_level='DEBUG', streamh_level='INFO')

# ===============================================
# Helper Functions (DOI/URL/Names/Subarticles) - Unchanged
# ===============================================
def url_to_doi(url: str) -> str | None:
    """Extracts DOI from a PLOS URL after validation."""
    if validate_plos_url(url):
        try:
            if '?id=10.1371/' in url:
                return url.split('?id=')[-1].split('&')[0] # Extract DOI from query param
            elif url.startswith("https://doi.org/"):
                return url.split("https://doi.org/")[-1] # Extract DOI from direct doi.org link
            elif '/article?id=10.1371/' in url or '/peerReview?id=10.1371/' in url:
                 return url.split('?id=')[-1].split('&')[0]
        except Exception as e:
            logger.warning(f"Could not parse DOI from seemingly valid URL {url}: {e}")
            return url
        logger.warning(f"DOI pattern not recognized in valid URL: {url}")
        return url
    else:
        # Only log if it's not None or empty, otherwise it's expected
        if url: logger.warning(f"{url} was deemed an invalid url.")
        return url


def doi_to_short_doi(doi: str) -> str:
    """Returns the part after the last slash if DOI is valid."""
    if isinstance(doi, str) and validate_doi(doi):
        return doi.split('/')[-1]
    else:
        if isinstance(doi, str) and doi: # Log only if it's a non-empty string
             logger.warning(f"{doi} was deemed an invalid doi.")
        return str(doi) # Return string representation


def _get_author_names_fallback(article: Article) -> list:
    """Fallback helper to extract author names if Article.get_author_names is missing."""
    names = []
    # Check if article object and authors attribute exist before iterating
    # There are A LOT of articles whose author names will be skipped because they're not formatted correctly
    if not article or not hasattr(article, 'authors') or not article.authors:
         if article: logger.warning(f"Article object for {article.doi} missing 'authors' property or it's empty.")
         return names
    try:
        for contributor in article.authors:
            # Ensure contributor is a dict-like object
            if not isinstance(contributor, dict): continue
            given = contributor.get('given_names', '')
            surname = contributor.get('surname', '')
            full_name = f"{given} {surname}".strip()
            if not full_name:
                 full_name = contributor.get('group_name') or f"Unknown Author ({contributor.get('id', 'no id')})"
            names.append(full_name)
    except AttributeError as e: # Catch specific error if article object structure is wrong
        logger.error(f"Fallback failed: AttributeError accessing authors for {article.doi}: {e}")
    except Exception as e_auth: # Catch other potential errors
        logger.error(f"Error extracting author names via fallback for {article.doi}: {e_auth}")
    return names


def _extract_subarticles_fallback(article_tree: et._ElementTree) -> list:
    """Fallback helper to extract subarticles using XPath if Article.get_subarticles is missing."""
    if article_tree is None:
        logger.warning("Cannot extract subarticles, article tree is None.")
        return []
    try:
        # Find all sub-article elements anywhere in the tree
        return article_tree.xpath(".//sub-article")
    except Exception as e_sub:
        logger.error(f"Error extracting subarticles via fallback XPath: {e_sub}")
        return []

# ===============================================
# XML Parsing Functions - parse_subarticle Unchanged
# ===============================================
def parse_subarticle(root) -> dict:
    """Parses an lxml element representing a sub-article."""
    metadata = {}
    front = root.find('./front-stub') or root.find('./front')
    body = root.find('./body')

    if front is None or body is None:
        doi_elem = root.find('.//article-id[@pub-id-type="doi"]')
        doi_text = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else "Unknown DOI"
        logger.warning(f"Sub-article {doi_text} missing 'front(-stub)' or 'body'. Malformed XML? Skipping detailed parse.")
        metadata['type'] = root.get('article-type', 'unknown-malformed')
        metadata['doi'] = doi_text
        metadata['id'] = doi_to_short_doi(doi_text) if doi_text != "Unknown DOI" else f"malformed_{time.time_ns()}"
        return metadata

    metadata['type'] = root.get('article-type', 'unknown')
    metadata['specific_use'] = root.get('specific-use')

    doi_elem = front.find('.//article-id[@pub-id-type="doi"]')
    if doi_elem is not None and doi_elem.text:
         metadata['doi'] = doi_elem.text.strip()
    else:
         placeholder_doi = f"10.1371/journal.placeholder.{time.time_ns()}"
         logger.warning(f"Could not find DOI for sub-article type '{metadata['type']}'. Assigning placeholder: {placeholder_doi}")
         metadata['doi'] = placeholder_doi

    if metadata['type'] == 'aggregated-review-documents':
        title_elem = front.find('.//article-title')
        metadata['round'] = None
        if title_elem is not None and title_elem.text:
            try:
                match = re.search(r'round\s*#?(\d+)', title_elem.text.strip(), re.IGNORECASE)
                if match: metadata['round'] = int(match.group(1))
                else:
                    match_end = re.search(r'\b(\d+)$', title_elem.text.strip())
                    if match_end: metadata['round'] = int(match_end.group(1))
            except ValueError: logger.warning(f"Could not parse round number from title: '{title_elem.text.strip()}'")

    short_doi_part = doi_to_short_doi(metadata['doi'])
    metadata['id'] = short_doi_part
    if '.' in short_doi_part and short_doi_part.startswith('journal.'):
        parts = short_doi_part.split('.')
        if len(parts) >= 4 and parts[-1].startswith(('r', 'a')):
            try:
                id_num = int(parts[-1][1:])
                metadata['id'] = short_doi_part
            except (ValueError, IndexError):
                 logger.warning(f"Could not parse standard ID structure from {short_doi_part}, using full string.")
                 metadata['id'] = short_doi_part

    related_object = front.find('./related-object[@link-type="peer-reviewed-article"]')
    original_article_doi = None
    if related_object is not None:
        original_article_doi = related_object.get('document-id')
        if not original_article_doi: original_article_doi = related_object.get('{http://www.w3.org/1999/xlink}href')
    else:
         related_article = front.find('./related-article[@related-article-type="peer-reviewed"]')
         if related_article is not None: original_article_doi = related_article.get('{http://www.w3.org/1999/xlink}href')

    if original_article_doi and original_article_doi.startswith('info:doi/'):
         metadata['original_article_doi'] = original_article_doi[len('info:doi/'):]
    elif original_article_doi:
         metadata['original_article_doi'] = original_article_doi
    else:
         metadata['original_article_doi'] = None
         if '.' in metadata['doi']:
              parts = metadata['doi'].split('.')
              if len(parts) > 2 and parts[-1].startswith(('r','a','d')):
                   inferred_doi = ".".join(parts[:-1])
                   if validate_doi(inferred_doi):
                        logger.debug(f"Inferred original DOI {inferred_doi} from sub-article DOI {metadata['doi']}")
                        metadata['original_article_doi'] = inferred_doi

    date_elem = body.find('.//named-content[@content-type="Decision-Letter-Date"]') or \
                body.find('.//named-content[@content-type="Review-Date"]') or \
                body.find('.//named-content[@content-type="Author-Response-Date"]')
    if not date_elem: date_elem = body.find('.//named-content') or body.find('.//date')
    metadata['date'] = date_elem.text.strip() if date_elem is not None and date_elem.text else None

    if metadata['type'] == 'aggregated-review-documents':
        reviewers = []
        for p_elem in body.xpath('.//p[starts-with(normalize-space(.), "Reviewer #")]'):
             text = " ".join(p_elem.xpath(".//text()")).strip()
             try:
                 r = {}
                 num_match = re.search(r'Reviewer\s*#(\d+)', text, re.IGNORECASE)
                 if not num_match: continue
                 r['number'] = int(num_match.group(1))
                 name_part = text[num_match.end():].split(':', 1)[-1].strip()
                 if re.search(r'\b(No|not disclosed)\b', name_part, re.IGNORECASE): r['name'] = "Anonymous"
                 elif re.search(r'\b(Yes|disclosed)\b', name_part, re.IGNORECASE):
                     name_match = re.match(r'(?:Yes|disclosed)\s*[:\-]?\s*(.+)', name_part, re.IGNORECASE)
                     if name_match and name_match.group(1).strip(): r['name'] = name_match.group(1).strip()
                     else: r['name'] = "Disclosed, Name Not Provided"
                 else:
                     if len(name_part) > 5 and not re.match(r'^\s*[:\-(]', name_part): r['name'] = f"Disclosure Unclear ({name_part})"
                     else: r['name'] = "Disclosure Unclear"
                 reviewers.append(r)
             except Exception as e: logger.warning(f"Could not parse reviewer info line: '{text}'. Error: {e}")
        metadata['reviewers'] = reviewers

    supplementary = []
    main_article_doi = metadata.get('original_article_doi')
    if main_article_doi:
        main_short_doi = doi_to_short_doi(main_article_doi)
        for elem in body.xpath('.//supplementary-material'):
            sm_id_suffix = elem.get('id')
            if not sm_id_suffix:
                logger.warning(f"Supplementary material found in sub-article {metadata.get('id')} but missing 'id' attribute. Skipping.")
                continue
            sm_short_doi = f"journal.{main_short_doi}.{sm_id_suffix}"
            sm_doi = f"10.1371/{sm_short_doi}"
            sm_url = f"https://journals.plos.org/plosone/article/file?id={sm_doi}&type=supplementary" # Assume plosone, may need generalizing
            filename_elem = elem.find('.//named-content[@content-type="original-filename"]') or elem.find('.//named-content')
            original_filename = "unknown_filename"
            if filename_elem is not None and filename_elem.text: original_filename = filename_elem.text.strip()
            else:
                 caption_elem = elem.find('.//caption/p')
                 if caption_elem is not None and caption_elem.text:
                      if '.' in caption_elem.text.strip() and len(caption_elem.text.strip()) < 100: original_filename = caption_elem.text.strip()
            save_filename = sm_short_doi + get_extension_from_str(original_filename)
            supplementary.append({'id': sm_short_doi, 'doi': sm_doi, 'url': sm_url, 'original_filename': original_filename, 'filename': save_filename})
    metadata['supplementary_materials'] = supplementary
    return metadata


def parse_article_xml(xml_bytes: bytes, update: bool = False, skip_sm_dl: bool = False) -> dict:
    """
    Parses XML bytes for a PLOS article, creates an Article object manually,
    extracts metadata, identifies reviews, and handles file saving.
    Saves ONLY review-related content XML for reviewed articles.
    Retraction status is NOT checked here; it's handled by the worker.
    """
    metadata = {}
    root = None
    doi = None
    a = None

    # --- Step 1: Parse XML Bytes ---
    try:
        parser = et.XMLParser(recover=True, strip_cdata=False, remove_blank_text=True)
        root = et.fromstring(xml_bytes, parser=parser)
        if root is None: raise ValueError("lxml parsing returned None.")
    except et.XMLSyntaxError as e:
        logger.error(f"XML Syntax Error during parsing: {e}", exc_info=False)
        return {}
    except ValueError as e:
        logger.error(f"XML Parsing ValueError: {e}")
        return {}
    except Exception as e:
        logger.error(f"Unexpected error during initial XML parsing: {e}", exc_info=True)
        return {}

    # --- Step 2: Extract DOI ---
    try:
        doi_elem = root.find('.//article-id[@pub-id-type="doi"]')
        if doi_elem is not None and doi_elem.text:
            doi = doi_elem.text.strip()
            if not validate_doi(doi): doi = None
        if not doi:
            all_ids = root.findall(".//article-id")
            for id_elem in all_ids:
                if id_elem.text:
                     potential_doi = id_elem.text.strip()
                     if validate_doi(potential_doi):
                          doi = potential_doi; break
            if not doi:
                 logger.error("Could not find any valid DOI in XML structure.")
                 return {}
    except Exception as e:
        logger.error(f"Error extracting DOI from XML structure: {e}", exc_info=True)
        return {}

    # --- Step 3: Create Article Object Manually ---
    try:
        a = Article(doi)
        a._tree = et.ElementTree(root)
        a_short_doi = doi_to_short_doi(a.doi)
    except Exception as e:
        logger.error(f"Failed to create Article object for DOI {doi}: {e}", exc_info=True)
        return {}

    # --- Step 4: Extract Basic Metadata ---
    try:
        metadata['doi'] = a.doi
        metadata['title'] = getattr(a, 'title', 'Title Not Found')
        metadata['url'] = getattr(a, 'page', None)
        metadata['fulltext_xml_url'] = getattr(a, 'url', None)
        journal_title = getattr(a, 'journal', 'Unknown Journal')
        journal_volume = getattr(a, 'volume', None)
        journal_issue = getattr(a, 'issue', None)
        metadata['journal'] = {'title': journal_title, 'volume': journal_volume, 'issue': journal_issue}
        pubdate = getattr(a, 'pubdate', None)
        metadata['publication_date'] = {'year': pubdate.year, 'month': pubdate.month, 'day': pubdate.day} if pubdate else None
        metadata['authors'] = _get_author_names_fallback(a)
        metadata['keywords'] = getattr(a, 'categories', [])
        metadata['retracted'] = None # Initialize retraction status as None (will be set by worker)
    except AttributeError as e:
         logger.error(f"Missing attribute extracting basic metadata for {a.doi}: {e}.")
    except Exception as e:
         logger.error(f"Error extracting basic metadata for {a.doi}: {e}", exc_info=False)

    # --- Step 5: Sub-article Processing ---
    article_tree = getattr(a, 'tree', None)
    sub_articles_list = _extract_subarticles_fallback(article_tree)

    if sub_articles_list:
        metadata['has_reviews'] = True
        metadata['sub_articles'] = []
        try:
            if hasattr(a, 'get_page'): metadata['reviews_url'] = a.get_page('peerReview')
            else: metadata['reviews_url'] = None
        except Exception: metadata['reviews_url'] = None

        article_dir = os.path.join(filtered_path, a_short_doi)
        sub_articles_dir = os.path.join(article_dir, 'sub-articles')

        # Determine if files should be written based on update flag and dir existence
        write_files = True
        if os.path.exists(article_dir) and not update:
            write_files = False
        elif not os.path.exists(article_dir):
            try: os.makedirs(sub_articles_dir, exist_ok=True)
            except OSError as e: logger.error(f"Failed create dir {article_dir}: {e}"); write_files = False
        elif update: # Dir exists and update=True
            try: os.makedirs(sub_articles_dir, exist_ok=True) # Ensure sub-dir exists
            except OSError as e: logger.error(f"Failed ensure sub-dir exists {sub_articles_dir}: {e}"); write_files = False

        parsed_sub_article_metadata_list = []
        elements_to_aggregate = []

        for sub_a_element in sub_articles_list:
            if not et.iselement(sub_a_element): continue
            sub_a_metadata = parse_subarticle(sub_a_element)
            if not sub_a_metadata: continue
            if sub_a_metadata.get('specific_use') == 'acceptance-letter': continue

            metadata['sub_articles'].append(sub_a_metadata)
            parsed_sub_article_metadata_list.append(sub_a_metadata)
            elements_to_aggregate.append(sub_a_element)

            # --- Handle SM Downloads ---
            # This is still a problem because while it identified SM files, it always fails to download them
            if write_files and not skip_sm_dl and 'supplementary_materials' in sub_a_metadata and sub_a_metadata['supplementary_materials']:
                for sm in sub_a_metadata['supplementary_materials']:
                    sm_filepath = os.path.join(sub_articles_dir, sm['filename'])
                    if os.path.exists(sm_filepath) and not update: continue
                    if not sm.get('url') or not validate_plos_url(sm['url']):
                         logger.warning(f"Invalid SM URL for {sm.get('original_filename','?')}: {sm.get('url')}")
                         continue
                    logger.info(f"Downloading SM {sm['original_filename']} for {a_short_doi}")
                    try:
                        r = requests.get(sm['url'], stream=True, timeout=60, headers={'User-Agent': 'PLOSCrawler/1.0'})
                        r.raise_for_status()
                        with open(sm_filepath, 'wb') as fp_sm:
                            for chunk in r.iter_content(chunk_size=8192): fp_sm.write(chunk)
                    except requests.exceptions.RequestException as e_req: logger.error(f"Failed download SM {sm['filename']}: {e_req}")
                    except IOError as e_io: logger.error(f"Failed write SM {sm['filename']}: {e_io}")
                    except Exception as e_sm: logger.error(f"Unexpected error download SM {sm['filename']}: {e_sm}")

        # --- Create and Save Aggregated Reviews-Only XML ---
        if write_files and elements_to_aggregate:
            reviews_only_root = et.Element("peer-review-content")
            reviews_only_root.set("original-article-doi", metadata.get('doi', 'unknown'))
            sub_articles_appended_count = 0
            for sub_a_element in elements_to_aggregate:
                 try:
                     reviews_only_root.append(copy.deepcopy(sub_a_element))
                     sub_articles_appended_count += 1
                 except Exception as e_copy: logger.error(f"Failed deep copy sub-article for {metadata.get('doi')}: {e_copy}")

            if sub_articles_appended_count > 0:
                reviews_only_tree = et.ElementTree(reviews_only_root)
                reviews_only_xml_path = os.path.join(article_dir, f"{a_short_doi}.xml")
                logger.info(f"Saving aggregated peer review XML ({sub_articles_appended_count} items) to {reviews_only_xml_path}")
                try:
                    reviews_only_tree.write(reviews_only_xml_path, encoding='utf-8', xml_declaration=True, pretty_print=True)
                except Exception as e_write_reviews: logger.error(f"Failed write aggregated reviews XML {reviews_only_xml_path}: {e_write_reviews}")
            else: logger.warning(f"No suitable sub-articles to save in aggregated XML for {metadata.get('doi')}")

        # --- Save Individual Sub-Article JSON Metadata ---
        if write_files:
            for sub_a_meta in parsed_sub_article_metadata_list:
                original_sub_a_id = sub_a_meta.get('id', f"unknown_id_{time.time_ns()}")
                safe_sub_a_filename_base = original_sub_a_id.replace('/', '_').replace('\\', '_').replace(':', '_')
                sub_a_json_filename = safe_sub_a_filename_base + '.json'
                sub_a_json_path = os.path.join(sub_articles_dir, sub_a_json_filename)
                try:
                    with open(sub_a_json_path, 'w', encoding='utf-8') as fp_json:
                        json.dump(sub_a_meta, fp_json, indent=4)
                except Exception as e_json:
                    logger.error(
                        f"Failed write sub-article JSON for original ID '{original_sub_a_id}' (tried filename: '{sub_a_json_filename}'): {e_json}")

        # --- Save Main Article Metadata ---
        if write_files:
            main_json_path = os.path.join(article_dir, "metadata.json")
            try:
                if 'sub_articles' not in metadata: metadata['sub_articles'] = []
                with open(main_json_path, 'w', encoding='utf-8') as fp_main_json: json.dump(metadata, fp_main_json, indent=4)
            except Exception as e_json_main: logger.error(f"Failed write main metadata.json for {a_short_doi}: {e_json_main}")

    else: # No sub-articles found
        metadata['has_reviews'] = False

    # --- Step 6: Save Basic Metadata to all_articles Directory ---
    all_articles_json_path = os.path.join(all_articles_path, a_short_doi + ".json")
    should_write_all_meta = True
    if os.path.exists(all_articles_json_path):
        if not update: should_write_all_meta = False

    if should_write_all_meta:
        try:
            os.makedirs(all_articles_path, exist_ok=True)
            if metadata is None: metadata = {'doi': doi if doi else 'unknown_doi'}
            with open(all_articles_json_path, 'w', encoding='utf-8') as fp_all_json: json.dump(metadata, fp_all_json, indent=4)
        except Exception as e_all_json: logger.error(f"Failed write initial basic metadata to {all_articles_json_path}: {e_all_json}")

    return metadata

# ===============================================
# Worker Function for Parallel Processing - Uses CSV set
# ===============================================
def process_single_xml_file(filename, input_dir, all_articles_path, filtered_path, options, retracted_dois_set):
    """
    Processes a single XML file. Reads, parses, sets retraction status from CSV set,
    and triggers saves via parse_article_xml. Re-saves final metadata.
    Returns a tuple: (status, doi, has_reviews)
    This slows things down as it basically performs 2 write operations!
    """
    short_doi = os.path.splitext(os.path.basename(filename))[0]
    full_path = os.path.join(input_dir, filename)
    log_prefix = f"[{os.getpid()}] "

    # --- Skipping Logic ---
    metadata_file_path = os.path.join(all_articles_path, short_doi + ".json")
    if not options.get('update', False) and os.path.exists(metadata_file_path):
         if not options.get('rescan_reviewed', False):
             logger.debug(f"{log_prefix}Skipping: {filename} (Basic metadata exists, update=False)")
             return ('skipped', short_doi, None)

    xml_bytes = None
    try:
        with open(full_path, 'rb') as fp:
            xml_bytes = fp.read()

        if not xml_bytes:
            logger.warning(f"{log_prefix}File {filename} is empty.")
            return ('empty', short_doi, None)

        # Call the main parsing function (retraction check removed from here)
        metadata = parse_article_xml(
            xml_bytes,
            update=options.get('update', False),
            skip_sm_dl=options.get('skip_sm_dl', False)
        )

        if metadata:
            # --- Set Retraction Status Post-Parsing ---
            article_doi = metadata.get('doi')
            if article_doi and article_doi.lower() in retracted_dois_set: # Compare lowercase
                metadata['retracted'] = True
                logger.debug(f"{log_prefix}Marking {article_doi} as retracted (from CSV).")
            else:
                metadata['retracted'] = False

            # --- Re-save Basic Metadata with Final Retraction Status ---
            a_short_doi = doi_to_short_doi(article_doi) if article_doi else short_doi
            final_metadata_path = os.path.join(all_articles_path, a_short_doi + ".json")
            try:
                 with open(final_metadata_path, 'w', encoding='utf-8') as fp:
                    json.dump(metadata, fp, indent=4)
            except Exception as e:
                logger.error(f"{log_prefix}Failed to write/update final basic metadata to {final_metadata_path}: {e}")

            return ('processed', a_short_doi, metadata.get('has_reviews', False))
        else:
            logger.error(f"{log_prefix}Parsing failed for {filename} (returned empty metadata).")
            return ('error', short_doi, None)

    except FileNotFoundError:
        logger.error(f"{log_prefix}File not found: {full_path}")
        return ('error', short_doi, None)
    except Exception as e:
        logger.error(f"{log_prefix}Unhandled exception processing {filename}: {e}", exc_info=True)
        return ('error', short_doi, None)
    finally:
        if 'xml_bytes' in locals() and xml_bytes is not None:
            del xml_bytes

# ===============================================
# Main Processing Orchestration - Includes Auto-Download
# ===============================================
def process_allofplos(update: bool = False, rescan_reviewed: bool = False, skip_sm_dl: bool = False):
    """Orchestrates the processing of PLOS articles using multiprocessing and auto-updating CSV retraction check."""
    start_time = time.time()
    logger.info(f"--- Starting PLOS Processing (Parallel + Auto-Updating CSV Retraction) ---")
    options = {
        'update': update,
        'rescan_reviewed': rescan_reviewed,
        'skip_sm_dl': skip_sm_dl,
    }
    logger.info(f"Options: {options}")
    logger.info(f"Output dirs: All Articles='{all_articles_path}', Filtered='{filtered_path}'")
    logger.info(f"Using Input Directory: {default_extract_dir}")

    # --- Define CSV Path and URL ---
    csv_file_path = 'retraction_watch.csv' # Local filename to save/read
    csv_download_url = 'https://gitlab.com/crossref/retraction-watch-data/-/raw/main/retraction_watch.csv'

    # --- Attempt to Download Latest Retraction CSV --- #
    logger.info(f"Attempting to download latest retraction data from {csv_download_url}...")
    try:
        response = requests.get(csv_download_url, timeout=60)
        response.raise_for_status()

        # Basic check for valid content
        if response.content and 'OriginalPaperDOI' in response.text:
             with open(csv_file_path, 'wb') as f:
                 f.write(response.content)
             logger.info(f"Successfully downloaded and saved latest retraction data to {csv_file_path}")
        else:
             # Log if content seems empty or lacks expected header
             logger.warning(f"Downloaded retraction data from {csv_download_url} seems invalid or empty (Status: {response.status_code}). Will proceed using local file if it exists.")
             if not os.path.exists(csv_file_path):
                  logger.error(f"Download failed/invalid and local file {csv_file_path} does not exist. Retraction check will be empty.")

    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to download latest retraction data: {e}")
        if os.path.exists(csv_file_path):
            logger.warning(f"Proceeding with existing local file: {csv_file_path}")
        else:
            logger.error(f"Download failed and local file {csv_file_path} does not exist. Retraction check will be empty.")
    except Exception as e_dl:
        logger.error(f"An unexpected error occurred during CSV download: {e_dl}")
        if os.path.exists(csv_file_path):
            logger.warning(f"Proceeding with existing local file: {csv_file_path}")
        else:
             logger.error(f"Download failed and local file {csv_file_path} does not exist. Retraction check will be empty.")

    # --- Load Retracted DOIs from LOCAL CSV (most updated one!) ---
    logger.info(f"Loading retracted DOIs from local file: {csv_file_path}...")
    retracted_dois_set = set()
    try:
        with open(csv_file_path, mode='r', encoding='utf-8', errors='ignore') as csvfile:
            reader = csv.DictReader(csvfile)
            if 'OriginalPaperDOI' not in reader.fieldnames:
                logger.error(f"'OriginalPaperDOI' column not found in {csv_file_path}. Cannot check retractions.")
            else:
                count = 0
                for row in reader:
                    doi = row.get('OriginalPaperDOI')
                    if doi:
                         retracted_dois_set.add(doi.strip().lower())
                         count += 1
                logger.info(f"Loaded {len(retracted_dois_set)} unique retracted DOIs from {count} rows found in {csv_file_path}.")
    except FileNotFoundError:
        logger.error(f"Local file {csv_file_path} not found after download attempt. Retraction status will be set to False.")
    except Exception as e:
        logger.error(f"Error reading local CSV file {csv_file_path}: {e}", exc_info=True)

    # --- Get List of Files to Process ---
    logger.info("Gathering list of files to process...")
    files_to_process = []
    try:
        if not os.path.isdir(default_extract_dir):
             logger.error(f"Input directory '{default_extract_dir}' not found or is not a directory. Cannot proceed.")
             return

        all_files_in_source = [
            f for f in os.listdir(default_extract_dir)
            if os.path.isfile(os.path.join(default_extract_dir, f)) and f.lower().endswith('.xml')
        ]
        logger.info(f"Found {len(all_files_in_source)} XML files in source directory.")

        if rescan_reviewed:
            reviewed_dois = set()
            if os.path.exists(filtered_path):
                try:
                    reviewed_dois = {d for d in os.listdir(filtered_path) if os.path.isdir(os.path.join(filtered_path, d))}
                    logger.info(f"Rescan: Found {len(reviewed_dois)} reviewed article directories.")
                except OSError as e: logger.warning(f"Could not list reviewed directory '{filtered_path}': {e}")
            else: logger.warning(f"Rescan reviewed requested, but directory '{filtered_path}' not found.")
            files_to_process = [f for f in all_files_in_source if os.path.splitext(os.path.basename(f))[0] in reviewed_dois]
            logger.info(f"Rescanning: {len(files_to_process)} files selected for processing.")
        else:
             files_to_process = all_files_in_source
             if not update:
                 logger.info("Pre-filtering files based on existing metadata (update=False)...")
                 original_count = len(files_to_process)
                 actually_process = []
                 skipped_count_prefilter = 0
                 for f in files_to_process:
                      short_doi = os.path.splitext(os.path.basename(f))[0]
                      metadata_file_path = os.path.join(all_articles_path, short_doi + ".json")
                      if not os.path.exists(metadata_file_path):
                           actually_process.append(f)
                      else:
                          skipped_count_prefilter += 1
                 files_to_process = actually_process
                 logger.info(f"Skipped {skipped_count_prefilter} files via pre-filtering. Processing {len(files_to_process)} files.")

        if not files_to_process:
             logger.info("No files selected for processing.")
             return

    except Exception as e:
        logger.error(f"Error gathering file list: {e}", exc_info=True)
        return

    # --- Setup Multiprocessing Pool ---
    try:
        num_workers = os.cpu_count()
        logger.info(f"Initializing processing pool with {num_workers} workers.")
    except NotImplementedError:
        logger.warning("os.cpu_count() not implemented. Defaulting to 1 worker.")
        num_workers = 1

    # Use functools.partial to pass the retracted DOI set
    worker_func = partial(
        process_single_xml_file,
        input_dir=default_extract_dir,
        all_articles_path=all_articles_path,
        filtered_path=filtered_path,
        options=options,
        retracted_dois_set=retracted_dois_set # pass the loaded set
    )

    processed_counter = 0
    reviewed_counter = 0
    errors_counter = 0
    skipped_counter = 0
    empty_counter = 0
    processed_dois_set = set()

    # --- Run Tasks in Parallel ---
    pool = None
    try:
        pool = multiprocessing.Pool(processes=num_workers)
        logger.info(f"Submitting {len(files_to_process)} tasks to the pool...")
        results = pool.imap_unordered(worker_func, files_to_process)

        for i, result in enumerate(results):
            if (i + 1) % 1000 == 0 or (i + 1) == len(files_to_process):
                 elapsed = time.time() - start_time
                 rate = (i + 1) / elapsed if elapsed > 0 else 0
                 logger.info(f"Progress: Handled ~{i+1}/{len(files_to_process)} results... ({rate:.2f} files/sec)")

            if result:
                status, doi, has_reviews = result
                if status == 'processed':
                    processed_counter += 1
                    if doi: processed_dois_set.add(doi)
                    if has_reviews:
                        reviewed_counter += 1
                elif status == 'skipped':
                    skipped_counter += 1
                elif status == 'empty':
                    empty_counter += 1
                elif status == 'error':
                    errors_counter += 1
            else:
                errors_counter += 1
                logger.error("Worker returned unexpected None result.")

    except KeyboardInterrupt:
         logger.warning("KeyboardInterrupt received. Terminating pool...")
         if pool:
             pool.terminate()
         logger.warning("Pool terminated.")
    except Exception as e:
        logger.error(f"Error during parallel processing execution: {e}", exc_info=True)
        if pool:
            pool.terminate()
    finally:
        if pool:
            pool.close()
            pool.join()
            logger.info("Processing pool closed.")

    # --- Log Summary ---
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"--- Processing Summary (Parallel + Auto-Updating CSV Retraction) ---")
    logger.info(f"Finished processing in {duration:.2f} seconds.")
    logger.info(f"Total files submitted to pool: {len(files_to_process)}")
    logger.info(f"Files processed successfully (parsing OK): {processed_counter}")
    logger.info(f"Files skipped by workers (e.g., exists & update=False): {skipped_counter}")
    logger.info(f"Reviewed articles found/processed this run: {reviewed_counter}")
    logger.info(f"Empty files encountered: {empty_counter}")
    logger.info(f"Files with processing/parsing errors: {errors_counter}")
    logger.info(f"--------------------------")


# ===============================================
# Main Execution Block
# ===============================================
if __name__ == '__main__':
    # Sets up argument parsing
    parser = argparse.ArgumentParser(
        description="Process PLOS articles using parallel processing and auto-updating CSV-based retraction check. Extracts metadata and aggregated review XML.",
        epilog="Example: python plos_crawler_autocsv.py --update --skip-sm-dl" # Updated example script name
    )
    parser.add_argument('--download', action='store_true', help='Download the allofplos corpus zip file (run separately).')
    parser.add_argument('--unzip', action='store_true', help='Unzip the allofplos corpus (run separately).')
    parser.add_argument('--update', action='store_true', help='Overwrite existing metadata and article files.')
    parser.add_argument('--rescan-reviewed', action='store_true', help='Only process articles whose DOIs match directory names already present in the reviewed_articles output directory.')
    parser.add_argument('--skip-sm-dl', action='store_true', help='Skip downloading supplementary materials for sub-articles.')

    args = parser.parse_args()

    if args.download or args.unzip:
        logger.warning("--download and --unzip flags are ignored in this parallel script.")
        logger.warning("Please download and unzip the corpus separately before running.")

    # --- Run Main Processing ---
    process_allofplos(
        update=args.update,
        rescan_reviewed=args.rescan_reviewed,
        skip_sm_dl=args.skip_sm_dl
    )

    logger.info("PLOS Parallel Auto-CSV Crawler finished.")