#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "progressbar2"
# ]
# ///

import argparse
import logging
import urllib
from urllib.request import HTTPError, urlopen, urlretrieve
import json
import os
import threading
from progressbar import ProgressBar, streams

opener = urllib.request.build_opener()
opener.addheaders = [
    ('Accept', '*/*'),
    ('Accept-Encoding', '*'),
    ('Accept-Language', 'it-IT,it;q=0.9'),
    ('Cache-Control', 'no-cache'),
    ('Connection', 'keep-alive'),
    ('Pragma', 'no-cache'),
    ('Priority', 'u=5, i'),
    ('Referer', 'https://antenati.cultura.gov.it/'),
    ('Sec-Fetc-Dest', 'empty'),
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
        try:
            logging.debug('Downloading url %s', url)
            urlretrieve(url, full_path)
        except HTTPError as err:
            if err.code == 403:
                logging.error('403 error')
                url = url.replace(str(quality), str(round(quality / 2)))
                logging.debug('Downloading url %s', url)
                urlretrieve(url, full_path)
            else:
                raise


def get_archive_id(page: str):
    logging.debug('Getting the ID')
    string_to_find = "let windowsId = '"
    archive_id_index = page.find(string_to_find) + len(string_to_find)
    archive_id_len = 7
    archive_id = page[archive_id_index:archive_id_index + archive_id_len]
    logging.debug('The ID is: %s', archive_id)
    return archive_id


def get_path(metadata):
    return metadata['city'] + '/' + metadata['type'] + '/' + metadata['year']


def get_manifest(page: str):
    logging.debug('Getting the manifest')
    archive_id = get_archive_id(page)
    manifest_url = f'https://dam-antenati.cultura.gov.it/antenati/containers/{archive_id}/manifest'
    logging.debug('Manifest URL is: %s', manifest_url)
    response = urlopen(manifest_url)
    manifest = json.load(response)
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


def resolve_quality(quality_arg):
    if isinstance(quality_arg, int):
        return quality_arg
    elif quality_arg == 'high':
        return 2048
    elif quality_arg == 'low':
        return 512
    else:  # 'mid' default
        return 1024


def run_download(url, quality_arg, start_at, cancel_event=None, progress_callback=None, log_callback=None):
    """
    Core download logic, shared between CLI and GUI.

    cancel_event    : threading.Event — if set, the loop stops cleanly.
    progress_callback(current, total) : called after each page.
    log_callback(message)             : called with status strings.
    """
    def log(msg):
        logging.info(msg)
        if log_callback:
            log_callback(msg)

    log('Recupero pagina...')
    page = download_page(url)
    manifest = get_manifest(page)
    quality = resolve_quality(quality_arg)
    log(f'Qualità impostata a {quality}px')
    metadata = set_metadata(manifest)
    records = manifest['sequences'][0]['canvases']

    page_number = start_at
    last_page = metadata['pages'] + page_number - 1

    log('{city}: {type} ({year}) — {pages} pagine'.format(**metadata))

    for record in records:
        if cancel_event and cancel_event.is_set():
            log('Download annullato.')
            return False

        download_record(
            url=record['images'][0]['resource']['@id'],
            path=get_path(metadata),
            page_number=page_number,
            last_page=last_page,
            quality=quality,
        )

        if progress_callback:
            progress_callback(page_number, last_page)

        if page_number < last_page:
            page_number += 1

    log('Download completato.')
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def run_cli(args):
    streams.wrap_stderr()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    logging.debug('Booting up')

    page = download_page(args.url)
    manifest = get_manifest(page)
    quality = resolve_quality(args.quality)
    logging.debug('Quality set to %spx', quality)
    metadata = set_metadata(manifest)
    records = manifest['sequences'][0]['canvases']

    page_number = args.start_at
    last_page = metadata['pages'] + page_number - 1

    with ProgressBar(max_value=last_page) as progress_bar:
        print('{city}: {type} ({year})'.format(**metadata))
        for record in records:
            download_record(
                url=record['images'][0]['resource']['@id'],
                path=get_path(metadata),
                page_number=page_number,
                last_page=last_page,
                quality=quality,
            )
            if page_number < last_page:
                page_number += 1
                progress_bar.update(page_number)


# ── GUI ───────────────────────────────────────────────────────────────────────

def run_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox

    cancel_event = threading.Event()
    download_thread = None

    root = tk.Tk()
    root.title('Bradipo — Portale Antenati downloader')
    root.resizable(False, False)

    pad = {'padx': 10, 'pady': 5}

    # ── URL ──
    tk.Label(root, text='URL archivio', anchor='w').grid(row=0, column=0, sticky='w', **pad)
    url_var = tk.StringVar()
    tk.Entry(root, textvariable=url_var, width=60).grid(row=0, column=1, columnspan=2, sticky='ew', **pad)

    # ── Qualità ──
    tk.Label(root, text='Qualità', anchor='w').grid(row=1, column=0, sticky='w', **pad)
    quality_var = tk.StringVar(value='mid')
    quality_frame = tk.Frame(root)
    quality_frame.grid(row=1, column=1, columnspan=2, sticky='w', **pad)

    for label, value in [('Alta (2048px)', 'high'), ('Media (1024px)', 'mid'), ('Bassa (512px)', 'low')]:
        tk.Radiobutton(quality_frame, text=label, variable=quality_var, value=value).pack(side='left')

    tk.Label(quality_frame, text='  oppure px:').pack(side='left')
    custom_quality_var = tk.StringVar()
    tk.Entry(quality_frame, textvariable=custom_quality_var, width=6).pack(side='left')

    # ── Pagina iniziale ──
    tk.Label(root, text='Inizia dalla pagina', anchor='w').grid(row=2, column=0, sticky='w', **pad)
    start_at_var = tk.IntVar(value=1)
    tk.Spinbox(root, from_=1, to=9999, textvariable=start_at_var, width=6).grid(row=2, column=1, sticky='w', **pad)

    # ── Debug ──
    debug_var = tk.BooleanVar(value=False)
    tk.Checkbutton(root, text='Debug logging', variable=debug_var).grid(row=3, column=1, sticky='w', **pad)

    # ── Stato / progress ──
    progress_label_var = tk.StringVar(value='')
    tk.Label(root, textvariable=progress_label_var, anchor='w').grid(row=4, column=0, columnspan=3, sticky='w', **pad)
    progress_var = tk.DoubleVar(value=0)
    ttk.Progressbar(root, variable=progress_var, maximum=100, length=500).grid(
        row=5, column=0, columnspan=3, sticky='ew', **pad)

    # ── Log ──
    log_frame = tk.Frame(root)
    log_frame.grid(row=6, column=0, columnspan=3, sticky='ew', **pad)
    log_text = tk.Text(log_frame, height=8, width=70, state='disabled', wrap='word')
    scrollbar = tk.Scrollbar(log_frame, command=log_text.yview)
    log_text.configure(yscrollcommand=scrollbar.set)
    log_text.pack(side='left', fill='both', expand=True)
    scrollbar.pack(side='right', fill='y')

    # ── Pulsanti ──
    btn_frame = tk.Frame(root)
    btn_frame.grid(row=7, column=0, columnspan=3, pady=10)
    start_btn = tk.Button(btn_frame, text='Avvia download', width=18)
    start_btn.pack(side='left', padx=5)
    cancel_btn = tk.Button(btn_frame, text='Annulla', width=18, state='disabled')
    cancel_btn.pack(side='left', padx=5)

    # ── Helpers (thread-safe via root.after) ──

    def append_log(msg):
        log_text.configure(state='normal')
        log_text.insert('end', msg + '\n')
        log_text.see('end')
        log_text.configure(state='disabled')

    def safe_log(msg):
        root.after(0, append_log, msg)

    def safe_progress(current, total):
        pct = (current / total) * 100
        root.after(0, progress_var.set, pct)
        root.after(0, progress_label_var.set, f'Pagina {current} di {total}')

    def on_done_ui(success):
        start_btn.configure(state='normal')
        cancel_btn.configure(state='disabled')
        if success:
            progress_var.set(100)
            progress_label_var.set('Completato.')

    def get_quality():
        custom = custom_quality_var.get().strip()
        if custom:
            try:
                return int(custom)
            except ValueError:
                messagebox.showerror('Errore', 'Il valore di qualità personalizzato deve essere un intero.')
                return None
        return quality_var.get()

    def start_download():
        nonlocal download_thread
        url = url_var.get().strip()
        if not url:
            messagebox.showerror('Errore', 'Inserisci un URL.')
            return

        quality = get_quality()
        if quality is None:
            return

        logging.basicConfig(level=logging.DEBUG if debug_var.get() else logging.INFO)

        cancel_event.clear()
        progress_var.set(0)
        progress_label_var.set('')
        log_text.configure(state='normal')
        log_text.delete('1.0', 'end')
        log_text.configure(state='disabled')
        start_btn.configure(state='disabled')
        cancel_btn.configure(state='normal')

        def worker():
            try:
                success = run_download(
                    url=url,
                    quality_arg=quality,
                    start_at=start_at_var.get(),
                    cancel_event=cancel_event,
                    progress_callback=safe_progress,
                    log_callback=safe_log,
                )
                root.after(0, on_done_ui, success)
            except Exception as e:
                safe_log(f'Errore fatale: {e}')
                root.after(0, on_done_ui, False)

        download_thread = threading.Thread(target=worker, daemon=True)
        download_thread.start()

    def cancel_download():
        cancel_event.set()
        cancel_btn.configure(state='disabled')
        append_log('Annullamento in corso...')

    start_btn.configure(command=start_download)
    cancel_btn.configure(command=cancel_download)

    root.mainloop()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog='bradipo',
        description='Scarica registri dal Portale Antenati',
    )
    parser.add_argument('url',
                        nargs='?',
                        help="URL dell'archivio (facoltativo con --gui)")
    parser.add_argument('--gui',
                        action='store_true',
                        help="Apre l'interfaccia grafica")
    parser.add_argument('--debug',
                        action='store_true')
    parser.add_argument('--quality',
                        type=parse_level,
                        default='mid',
                        help="Qualità: 'high' (2048px), 'mid' (1024px), 'low' (512px) o un intero")
    parser.add_argument('--start-at',
                        type=int,
                        default=1)

    args = parser.parse_args()

    if args.gui:
        run_gui()
    else:
        if not args.url:
            parser.error("URL obbligatorio in modalità CLI (oppure usa --gui)")
        run_cli(args)


if __name__ == '__main__':
    main()
