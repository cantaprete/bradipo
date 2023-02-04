# Copyright (C) 2023 Jacopo Donati
# 
# This file is part of bradipo.
# 
# bradipo is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# bradipo is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with bradipo.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import logging
from urllib.request import Request, urlopen, urlretrieve
import json
import os
from progressbar import ProgressBar, streams


def download_page(url):
    logging.debug('Downloading page: ' + url)
    response = urlopen(url)
    html_bytes = response.read()
    page = html_bytes.decode('utf-8')
    return page

def download_record(url, path, page_number):
    logging.debug(f'Downloading page no. {page_number}')
    if not os.path.exists(path):
        os.makedirs(path)
    full_path = path + '/' + str(page_number).zfill(4) + '.jpg'
    if not os.path.exists(full_path):
        urlretrieve(url, full_path)

def get_archive_id(page):
    logging.debug('Getting the ID')
    string_to_find = 'let windowsId = \''
    id_index = page.find(string_to_find) + len(string_to_find)
    id_len = 7
    id = page[id_index:id_index+id_len]
    logging.debug('The ID is: ' + id)
    return id

def get_path(metadata):
    path = metadata['city'] + '/' + metadata['type'] + '/' + metadata['year']
    return path

def get_manifest(page):
    logging.debug('Getting the manifest')
    id = get_archive_id(page)
    manifest_url = f'https://dam-antenati.cultura.gov.it/antenati/containers/{id}/manifest'
    logging.debug('Manifest URL is: ' + manifest_url)
    request = Request(
        url = manifest_url,
        headers = {
            'Accept': '*/*',
            'Origin': 'https://antenati.cultura.gov.it',
            'Accept-Encoding': 'gzip, deflate, br',
            'Host': 'dam-antenati.cultura.gov.it',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.3 Safari/605.1.15',
            'Accept-Language': 'it-IT,it;q=0.9',
            'Referer': 'https://antenati.cultura.gov.it/',
            'Connection': 'keep-alive'
        }
        )
    with urlopen(request) as url:
        manifest = json.load(url)
        return manifest

def set_metadata(manifest):
    logging.debug('Setting metadata')
    context = manifest['metadata'][3]['value'].split(' > ')
    year = manifest['metadata'][2]['value'].split('/')
    year = year[0].split(' - ')
    metadata = {
        'year': year[0],
        'type': manifest['metadata'][1]['value'],
        'archive': context[0],
        'source': context[1],
        'city': context[2],
        'pages': len(manifest['sequences'][0]['canvases'])
    }
    return metadata

def main():
    parser = argparse.ArgumentParser(
                    prog = 'bradipo',
                    description = 'Downloads records from Portale Antenati',
                    )

    parser.add_argument('url',
                        help='URL of the archive')
    parser.add_argument('--debug',
                        action='store_true')
    parser.add_argument('--start-at',
                        type=int,
                        default=1)
    args = parser.parse_args()

    streams.wrap_stderr()
    if (args.debug):
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.debug('Booting up')
    page = download_page(args.url)
    manifest = get_manifest(page)
    metadata = set_metadata(manifest)
    records = manifest['sequences'][0]['canvases']

    logging.debug('Starting to download')
    page_number = args.start_at
    last_page = metadata['pages'] + page_number - 1
    with ProgressBar(max_value=last_page) as bar:
        print('{city}: {type} ({year})'.format(**metadata))
        for record in records:
            download_record(url = record['images'][0]['resource']['@id'],
                            path = get_path(metadata),
                            page_number = page_number)
            if (page_number < last_page):
                page_number = page_number + 1
                bar.update(page_number)


if __name__ == "__main__":
    main()