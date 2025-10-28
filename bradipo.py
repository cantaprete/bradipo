import argparse
import logging
import urllib
from urllib.request import Request, urlopen, urlretrieve
import json
import os
import re
from progressbar import ProgressBar, streams

opener = urllib.request.build_opener()
opener.addheaders = [
    ('Accept', '*/*'),
    ('Accept-Encoding', 'deflate, br'),
    ('Accept-Language', 'it-IT,it;q=0.9'),
    ('Cache-Control', 'no-cache'),
    ('Connection', 'keep-alive'),
    ('Pragma', 'no-cache'),
    ('Priority', 'u=5, i'),
    ('Referer', 'https://antenati.cultura.gov.it/'),
    ('Sec-Fetc-Dest', 'image'),
    ('Sec-Fetch-Mode', 'no-cors'),
    ('Sec-Fetch-Site', 'same-site'),
    ('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 Safari/605.1.15')
]
urllib.request.install_opener(opener)

def parse_level(value):
    s = value.lower()
    if s in {"high", "mid", "low"}:
        return s
    try:
        return int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "Invalid value: accepted values are 'high', 'mid', 'low' or an integer"
        )

def download_page(url: str):
    logging.debug('Downloading page: %s', url)
    response = urlopen(url)
    html_bytes = response.read()
    page = html_bytes.decode('utf-8')
    return page

def download_record(url: str, path: str, page_number: int, last_page: int, quality: int):
    logging.debug('Downloading page no. %s', page_number)
    if not os.path.exists(path):
        os.makedirs(path)
    padding = len(str(last_page))
    full_path = path + '/' + str(page_number).zfill(padding) + '.jpg'
    if not os.path.exists(full_path):
        parts = url.split('full', 2)
        url = parts[0] + 'full' + parts[1] + str(quality) + ',' + parts[2]
        logging.debug('Downloading url %s', url)
        urlretrieve(url, full_path)

def get_archive_id(page: str):
    logging.debug('Getting the ID')
    string_to_find = 'let windowsId = \''
    archive_id_index = page.find(string_to_find) + len(string_to_find)
    archive_id_len = 7
    archive_id = page[archive_id_index:archive_id_index+archive_id_len]
    logging.debug('The ID is: %s', archive_id)
    return archive_id

def get_path(metadata):
    path = metadata['city'] + '/' + metadata['type'] + '/' + metadata['year']
    return path

def get_manifest(page: str):
    logging.debug('Getting the manifest')
    archive_id = get_archive_id(page)
    manifest_url = f'https://dam-antenati.cultura.gov.it/antenati/containers/{archive_id}/manifest'
    logging.debug('Manifest URL is: %s', manifest_url)
    response = urlopen(manifest_url)
    manifest = json.load(response)
    return manifest

def set_metadata(manifest: str):
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
    parser.add_argument('--quality',
                        type=parse_level,
                        default='mid',
                        help="Set the quality to: 'high' (2048px), 'mid' (512px), 'low' (256px) or an integer"
    )
    parser.add_argument('--start-at',
                        type=int,
                        default=1)
    args = parser.parse_args()

    streams.wrap_stderr()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.debug('Booting up')
    page = download_page(args.url)
    manifest = get_manifest(page)
    quality = 1024
    if args.quality.isnumeric():
        quality = args.quality
    elif args.quality == 'high':
        quality = 2048
    elif args.quality == 'low':
        quality = 512
    metadata = set_metadata(manifest)
    records = manifest['sequences'][0]['canvases']

    logging.debug('Starting to download')
    page_number = args.start_at
    last_page = metadata['pages'] + page_number - 1
    with ProgressBar(max_value=last_page) as progress_bar:
        print('{city}: {type} ({year})'.format(**metadata))
        for record in records:
            download_record(url=record['images'][0]['resource']['@id'],
                            path=get_path(metadata),
                            page_number=page_number,
                            last_page=last_page,
                            quality=quality)
            if page_number < last_page:
                page_number = page_number + 1
                progress_bar.update(page_number)


if __name__ == "__main__":
    main()
