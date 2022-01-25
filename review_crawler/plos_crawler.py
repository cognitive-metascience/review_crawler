
"""test crawler for going through the "allofplos_xml.zip" file. The zip file should be in the same directory as this .py file.
Tries its best to detect which articles had been peer-reviewed, extracts them from the zip into filtered_dirname
Additionally, the sub-articles from each xml are extracted and saved into files in subarticles_dirname
"""

import json
import os
import zipfile
import xml.etree.cElementTree as ET

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