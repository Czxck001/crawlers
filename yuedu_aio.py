''' Crawler to grab articles and recitations from yuedu.fm
'''
import os
import re
import json

import asyncio
import aiohttp

import argparse

root = r'http://yuedu.fm'
channel_root = root + r'/channel/'
article_root = root + r'/article/'


async def article_page(session, page_url):
    ''' Return article text and recitation audio url
    '''
    while True:
        async with session.get(page_url) as response:
            if response.status >= 400:
                await asyncio.sleep(100)
                continue
            else:
                html = await response.text()
                break

    finding = re.findall(r'<div class="not-found">', html)
    if finding:  # page not found
        return None, None

    finding = re.findall(
        r'<span class="item-intro-hide"></span>'
        r'([\S\s]*)'
        r'</div>[\s]*<a href="javascript:;" class="item-intro-more fr">',
        html)
    if not finding:
        print('Article Content Not Found')
        return

    raw_article = finding[0]

    # remove html tags
    raw_article = re.sub(r'<[A-Za-z0-9/\-=":;\.\! ]*>', '', raw_article)

    lines = [line
             .replace(r'&gt;', '>')
             .replace(r'&lt;', '<')
             .replace(r'&igrave;', 'ì')
             .replace(r'&aacute;', 'á')
             .replace(r'&agrave;', 'à')
             .replace(r'&eacute;', 'é')
             .replace(r'&oacute;', 'ó')
             .replace(r'&bdquo;', '„')
             .replace(r'&not;', '¬')
             .replace(r'&bull;', '•')
             .replace(r'&amp;', '&')
             .replace(r'&ndash;', '–')
             .replace(r'&times;', '×')
             .replace(r'&#39;', "'")
             .replace(r'&middot;', '·')
             .replace(r'&quot;', '"')
             .replace(r'&lsquo;', '‘')
             .replace(r'&rsquo;', '’')
             .replace(r'&ldquo;', '“')
             .replace(r'&rdquo;', '”')
             .replace(r'&hellip;', '…')
             .replace(r'&mdash;', '—')
             .replace(r'&nbsp;', ' ')
             .strip()
             for line in raw_article.split('<br />')]

    article = '\n'.join('\n'.join(lines).split('\n'))

    # check if there is something left
    html_annotations = re.findall(r'(&.*;)', article) +\
        re.findall(r'<(.*)>', article)
    if html_annotations:
        print(page_url, html_annotations)

    finding = re.findall(r'mp3:"(.*)"', html)
    if not finding:
        print('Recitation Audio Not Found')
        return
    mp3_url = finding[0]

    return article, mp3_url


async def reader(session, article_index, queue):
    article, mp3_url = await article_page(
        session, article_root + '%d/' % article_index)
    if not article or not mp3_url:
        print('article %d: page not found')
    print('article %d: finished comprehension' % article_index)
    await queue.put((article_index, article, mp3_url))


async def writer(queue, outdir):
    if not os.path.isdir(outdir):
        os.mkdir(outdir)

    down_path = os.path.join(outdir, 'down.json')
    if not os.path.isfile(down_path):
        with open(down_path, 'w') as f:
            f.write('[]')

    while True:
        article_index, article, mp3_url = await queue.get()
        with open(os.path.join(outdir, '%d.txt' % article_index), 'w') as f:
            f.write(article)

        down = json.load(open(down_path))
        down.append({
            'url': root + mp3_url,
            'path': '%d.mp3' % article_index,
        })
        json.dump(down, open(down_path, 'w'), indent=4)
        print('Dumped %s' % mp3_url)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('yuedu.fm Crawler')
    parser.add_argument('-a', '--articles', type=int, nargs='*',
                        help='Article indexes')
    parser.add_argument('-r', '--article_range', type=int, nargs=2,
                        default=[0, 0],
                        help='Article indexes range (closed)')
    parser.add_argument('-o', '--outdir',
                        help='Output Folder Directory')

    FLAGS = parser.parse_args()

    if FLAGS.articles:
        indexes = FLAGS.articles
    else:
        l, r = FLAGS.article_range
        indexes = range(l, r + 1)

    loop = asyncio.get_event_loop()

    queue = asyncio.Queue()
    asyncio.ensure_future(writer(queue, FLAGS.outdir), loop=loop)
    with aiohttp.ClientSession(loop=loop) as session:
        # use asyncio.gather to bind tasks together
        reading = asyncio.gather(*[asyncio.ensure_future(
            reader(session, i, queue)) for i in indexes], loop=loop)
        loop.run_until_complete(reading)