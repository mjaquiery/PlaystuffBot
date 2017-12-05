import token

import requests, os, re, datetime, logging, discord
from lxml import html
from auth import token


def clean_date_field(date_field):
    rx = re.compile(r'([\d\w\-]+)')
    txt = rx.search(date_field)
    if txt:
        return txt.group(1)
    return date_field


def junk2datetime(date_str, time_str):
    h, mi = time_str.split(':')
    if date_str=='Yesterday' or date_str=='Today':
        dt = datetime.date.today()
        if date_str=='Yesterday':
            dt = dt - datetime.timedelta(days=1)
        d = dt.day
        mo = dt.month
        y = dt.year
    else:
        d, mo, y = date_str.split('-')

    return datetime.datetime(int(y), int(mo), int(d), int(h), int(mi))


def ints(non_int : list) -> list:
    list_out = []
    for x in non_int:
        try:
            x = int(x)
        except TypeError:
            continue
        finally:
            list_out.append(x)
    return list_out


def get_last_crawl_time() -> object:
    try:
        log_file = open(log_file_name, 'r')
        # reads the whole file into memory; probably excessive?
        for line in reversed(list(log_file)):
            date = re.match(r"[\d\-]{10} [\d:]{8}", line)
            if date:
                y, mo, d = ints(date.group()[0:10].split('-'))
                h, m, s = ints(date.group()[11:19].split(':'))
                return datetime.datetime(y, mo, d, h, m, s)
    except FileNotFoundError:
        pass
    # defaults to 'yesterday'
    return datetime.datetime.today() - datetime.timedelta(days=1)


def joinLists(a: list, b: list) -> list:
    if len(a) == 0:
        return b
    if len(b) == 0:
        return a
    for item in b:
        a.append(item)
    return a


def parse_thread(thread_url):
    log.debug(f"parse_thread: {thread_url.split('?')[0]}")
    new_posts = []
    index = requests.get(thread_url)
    tree = html.fromstring(index.content)
    posts = tree.xpath('//li[contains(@class, "postbitim")]')
    for post in posts:
        header = post.xpath('descendant::div[contains(@class, "posthead")]')[0]
        post_number = header.xpath('descendant::a[contains(@class, "postcounter")]')[0].text
        log.debug(f"Inspect post {post_number}")
        time_data = header.xpath('descendant::span[contains(@class, "date")]')[1]
        post_time = junk2datetime(clean_date_field(time_data.text),
                                  time_data.xpath('descendant::span[contains(@class, "time")]')[0].text)
        if post_time > last_checked:
            new_posts.append(post)
            log.debug(f"Post {post_number} is new.")

    if len(new_posts):
        # we have new posts, so check the previous page
        try:
            navbar = tree.xpath('//form[contains(@class, "pagination")]')[0]
            this_page = navbar.xpath('descendant::span[contains(@class, "selected")]/a[@href]')[0]
            pnum = this_page.text
            pages = navbar.xpath('//descendant::span/a[@href]')
            if int(pnum) > 1:
                for page in pages:
                    page_num = page.text
                    try:
                        if int(page_num)==int(pnum)-1:
                            prev_page_url = page.base + page.attrib['href']
                            new_posts = joinLists(new_posts, parse_thread(prev_page_url))
                            break
                    except (ValueError, TypeError):
                        continue
        except IndexError:
            pass  # we're already on the first page
    return new_posts


def parse_forum(forum_url):
    new_posts = []
    index = requests.get(forum_url)
    tree = html.fromstring(index.content)
    threads = tree.xpath('//li[contains(@class, "threadbit")]')
    for thread in threads:
        try:
            time_data = thread.xpath('descendant::dl[contains(@class,"threadlastpost")]/dd[2]')[0]
            post_time = junk2datetime(clean_date_field(time_data.text),
                                          time_data.xpath('descendant::span[contains(@class,"time")]')[0].text)
            if post_time > last_checked:
                url = thread.xpath('descendant::a[contains(@class,"lastpostdate")]')[0]
                url = url.base+url.attrib['href']
                new_posts = joinLists(new_posts, parse_thread(url))
        except IndexError:
            continue

    return new_posts


def parse_subfora(forum_url, depth=0):
    new_posts = []
    # Get the web data
    index = requests.get(forum_url)
    tree = html.fromstring(index.content)
    rows = tree.xpath('//li[contains(@class,"forumbit_post")]')

    for row in rows:
        buffer = '--' * depth
        title_data = row.xpath('descendant::h2[contains(@class,"forumtitle")]/a[@href]')[0]
        url = title_data.base+title_data.attrib['href']
        name = title_data.text
        try:
            time_data = row.xpath('descendant::p[contains(@class,"lastpostdate")]')[0]
            last_post = junk2datetime(clean_date_field(time_data.text),
                                          time_data.xpath('descendant::span[contains(@class,"time")]')[0].text)
            # Navigate to the forum and investigate the new posts
            new_posts = joinLists(new_posts, parse_forum(url))
            if not url == forum_url:
                new_posts = joinLists(new_posts, parse_subfora(url, depth+1))
        except IndexError:
            log.debug(f"{buffer}No access to {name} [{url.split('?')[0]}]")
            continue  # a forum which is displayed but doesn't give last-post dates is locked, so don't follow it
        # Find new posts
        log.debug(f"{buffer}{name} [{url.split('?')[0]}, ; {last_post}']")

    return new_posts


# Main
if __name__ == "__main__":
    global last_checked, log, log_file_name
    log_file_name = 'PSBot.log'
    last_checked = get_last_crawl_time()
    # last_checked = datetime.datetime.today() - datetime.timedelta(days=14)
    logging.basicConfig(filename=log_file_name, filemode='w', level=logging.INFO,
                        format='%(asctime)s.%(msecs)03d %(message)s')
    log = logging.getLogger("PSbot")
    new_posts = parse_subfora('http://playstuff.net/forum.php')
    log.info(f"Finished: found {int(len(new_posts))} new posts since {last_checked}")

    titles = {}
    for post in new_posts:
        title = post.xpath('descendant::h2[contains(@class, "title")]')[0].text.split()
        title = ' '.join(title)
        user = post.xpath('descendant::a[contains(@class, "username")]/*')[0].text.split()
        user = ' '.join(user)
        log.debug(f"{title} - {user}")
        if title not in titles:
            titles[title] = {'users':[user], 'posts':1}
        elif user not in titles[title]['users']:
            titles[title]['users'].append(user)
            titles[title]['posts'] += 1
        else:
            titles[title]['posts'] += 1

    speak_text = f"There are {len(new_posts)} new posts on http://playstuff.net/forum.php since "
    speak_text += f"{last_checked.strftime('%A, %d. %B %Y %I:%M%p')}"
    if len(new_posts):
        speak_text += ':'
        for title in titles:
            speak_text += f"\n{title} - {titles[title]['posts']} post"
            if titles[title]['posts'] > 1:
                speak_text += f"s from {len(titles[title]['users'])} \
                                user{'s' if len(titles[title]['users']) > 1 else ''}"
        log.debug(f"discord message: {speak_text}")
        # Announce new posts on Discord
        discord_bot_token = token.discord_bot_token
        server_id = "156752862888591360"  # playstuff server
        chat_id = "156752862888591360"  # chat channel
        client = discord.Client()
        @client.event
        async def on_ready():
            log.info(f"Logged into discord server {server_id} as {client.user.name} [{client.user.id}]")
            # Speak our piece
            await client.send_message(client.get_channel(chat_id), speak_text)
            # And be done
            client.logout()
            log.info(f"Logout")
            # raise SystemExit
        client.run(discord_bot_token)
