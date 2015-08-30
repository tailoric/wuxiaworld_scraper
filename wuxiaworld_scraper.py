#!/usr/bin/env python

import sys
import re
import time
import codecs

import requests
from bs4 import BeautifulSoup

reload(sys)
sys.setdefaultencoding('utf-8')


def process_index_page(url):
    ''' Processes the index page, returns the title, description, and starting
        element for BeautifulSoup parsing '''
    # Get source of index page and load into BS
    r_idx = requests.get(url)
    print "Default encoding: {}, forcing utf-8".format(r_idx.encoding)
    r_idx.encoding = 'utf-8'
    soup = BeautifulSoup(r_idx.text, 'html.parser')

    # Extract book name and links to chapters
    # Start with the entry-content div and go down from there
    start = soup.find('h1', {'class': 'entry-title'})

    # Grab the title (the English part before the "(")
    title = start.text.split('(')[0].strip()

    print "Fetching {}...".format(title)

    # Grab the description
    desc = start.find_next("p").text

    return (title, desc, start)


def run_pandoc_on(filenames):
    ''' Runs pandoc on the resulting html files '''
    import subprocess

    for fn in filenames:
        try:
            cmdl = ['pandoc', '-f', 'html', '-t', 'epub', fn,
                    '-o', fn.replace('.html', '.epub')]
            print "Command: {}".format(" ".join(cmdl))
            subprocess.call(cmdl)
            print 'Successfully converted {} to epub!'.format(fn)
        except subprocess.CalledProcessError:
            print 'Converting to epub failed for {}. Skipping...'.format(fn)


def scrape(url, books, delay, skip_epub):
    ''' Scrapes the given URL and creates combined HTML file '''
    # Process index page
    title, desc, start = process_index_page(url)

    # Save filenames for conversion later
    fnames = []

    # book names are between <strong> tags
    for elem in start.find_all_next('strong'):

        if elem.text.split()[0] == "Book":

            # Skip unwanted books
            booknum = elem.text.split()[1]
            if books and int(booknum) not in books:
                print "Skipping Book {}...".format(booknum)
                continue

            print "Processing Book {}".format(booknum)

            # This is a book!  Open a new HTML file and write some metadata
            fname = "".join(title.split()) + elem.text.split()[0] + elem.text.split()[1].zfill(2) + ".html"
            fnames.append(fname)
            # Use codecs.open to ensure we maintain unicode throughout
            with codecs.open(fname, 'w', 'utf-8') as out:
                html_title = title + ": " + elem.text
                out.write(('<html>\n<head>\n<meta charset="utf-8">\n<meta name'
                           '="description" content="{}">\n<title>{}</title>\n'
                           '</head>\n<body>').format(desc, html_title))

                # Now request each chapter and extract the content
                # NOTE: This could be parallelized, but we don't want to get banned!
                #       A scraper might get banned anyway...
                for ch_url in elem.find_all_next(True):
                    # If it's a horizontal rule or a strong, there's a new book
                    if ch_url.name in ['hr', 'strong']:
                        print "Found end of Book {}...".format(booknum)
                        break
                    # If it's something other than an anchor, skip it
                    elif ch_url.name != 'a':
                        continue

                    time.sleep(delay)  # Slow down a bit so we don't get banned
                    r_chap = requests.get(ch_url.get('href'))
                    r_chap.encoding = 'utf-8'
                    ch_soup = BeautifulSoup(r_chap.text, 'html.parser')
                    first_el = ch_soup.find(True)
                    this_strong = first_el
                    this_bold = first_el
                    tmp = ''
                    tries = 0
                    ch_title = ''
                    while not ch_title:
                        tries += 1
                        if this_strong:
                            try:
                                this_strong = this_strong.find_next("strong")
                                tmp = this_strong.text.strip()
                            except AttributeError:
                                pass
                        elif this_bold:
                            try:
                                this_bold = this_bold.find_next("b")
                                tmp = this_bold.text.strip()
                            except AttributeError:
                                pass
                        else:
                            print "Could not find any strong or bold elements with the title inside!"
                            print "Check source for {} and update code.".format(ch_url.get('href'))
                            sys.exit(-1)
                        try:
                            # Coiling Dragon-style chapter titles
                            if tmp.split()[0] == "Book":
                                ch_title = tmp[tmp.find("Chapter"):].replace("Chapter", "Ch.")
                                print "Chapter title: {}".format(ch_title)
                                continue
                            # Stellar Transformations-style chapter titles
                            elif re.match('B[0-9]+C[0-9]+', tmp):
                                ch_title = re.sub('B[0-9]+C', 'Ch. ', tmp)
                                print "Chapter title: {}".format(ch_title)
                        except IndexError:
                            pass

                        if tries > 50:
                            print "Could not find title! Check source for {} and update code.".format(ch_url)
                            sys.exit(-1)

                    # Put chapter title in h1 so the epub converter will see it as a chapter
                    out.write('\n\n<h1>{}</h1>\n'.format(ch_title))

                    # Then loop through each next element and plop it in there
                    # until we hit a horizontal rule
                    start_tag = ch_soup.find("hr")
                    start_tag = start_tag.find_next(True)
                    for p in start_tag.find_all_next(True):
                        if p.name == "hr":
                            break
                        elif p.name == "p":
                            # Some chapters don't have the hr, so make sure it
                            # doesn't have any links (the prev/next chapter links)
                            clist = list(p.children)
                            if len(clist) > 0:
                                ctags = [child.name for child in clist]
                                if "a" in ctags:
                                    break
                            out.write(unicode(p))
                            out.write("\n")

                # Close out html
                out.write("\n\n</body>\n</html>\n")

    # Optionally run pandoc
    if not skip_epub:
        run_pandoc_on(fnames)


def main():
    ''' Take arguments and run scraper '''
    import argparse

    parser = argparse.ArgumentParser(description='Wuxiaworld Scraper')
    parser.add_argument('url', help='Index page of story to scrape',
                        default='http://www.wuxiaworld.com/cdindex-html')
    parser.add_argument('--delay', default=1,
                        help=('Delay between scraping chapters (don\'t wanna '
                              'get banned!)'))
    parser.add_argument('--books', nargs='+', type=int, default=None,
                        help='The books to download (defaults to all)')
    parser.add_argument('--no-epub', action='store_false',
                        help=('Automatically run pandoc to convert to epub. '
                              '(Requires pandoc on path)'))
    args = parser.parse_args()

    scrape(args.url, args.books, args.delay, args.no_epub)

if __name__ == "__main__":
    main()