import datetime
import json
import time
import argparse
import requests
import psycopg2

from typing import List
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from telegram.ext.callbackcontext import CallbackContext
from telegram.update import Update
from telegram.error import Unauthorized

from lib.config import Config
from lib.log import get_logger
from lib.question import Question
from lib.stats import set_startup, get_stats

MAX_TRIES = 3
WAIT_BETWEEN_TRIES = 3

PAGE_SIZE = 100  # Max valid value

MODE_EMPTY = 0
MODE_TAGS = 1
MODE_TAGS_ALL = 2
MODE_TAGS_EXCLUDE = 2

global conn
global site_list
global handler_log
global api_log
global config
global is_running


def set_connect(cfg: Config):
    global conn
    conn = psycopg2.connect(dbname=cfg.db_name, user=cfg.db_user,
                            password=cfg.db_password, host=cfg.db_host, port=cfg.db_port)
    return conn


def get_connect():
    global conn
    return conn


def set_sites(sites):
    global site_list
    connect = get_connect()
    cur = connect.cursor()
    for i in sites:
        if i not in site_list:
            cur.execute("select id from stackexchange_db.sites where api_site_parameter = %s", (i,))
            buf = cur.fetchone()
            if buf is None:
                cur.execute("insert into stackexchange_db.sites(api_site_parameter) values (%s) returning id", (i,))
                buf, = cur.fetchone()
            else:
                buf = buf[0]
            site_list[i] = buf
    connect.commit()


def other_bots(update: Update, context: CallbackContext):
    global handler_log
    handler_log.info("Received other_bots command from user {}".format(update.effective_chat.id))
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="You can may be interested in my other telegram bots: "
                                  " https://t.me/idle_rpg_bot - simple ZPG"
                                  " https://t.me/achievement_hunt_bot - game achievement rarity checker.")


def start(update: Update, context: CallbackContext):
    global handler_log
    handler_log.info("Received start command from user {}".format(update.effective_chat.id))
    help_response(update, context)


def sources(update: Update, context: CallbackContext):
    global handler_log
    handler_log.info("Received sources command from user {}".format(update.effective_chat.id))
    msg = "Bot sources available on https://github.com/qvant/stackexchange_bot."
    context.bot.send_message(text=msg,
                             chat_id=update.effective_chat.id)


def help_response(update: Update, context: CallbackContext):
    global handler_log
    handler_log.info("Received help command from user {}".format(update.effective_chat.id))
    msg = "The bot supports following commands:" + chr(10)
    msg += "  /add - add subscription for the site from stackexchange network."
    msg += "  It has parameters:" + chr(10)
    msg += "    tags(or tags_any) - you will be notified about questions with any ot these tags " + chr(10)
    msg += "    tags_all - you will be notified about questions which has all these tags list" + chr(10)
    msg += "    tags_exclude - you wouldn't be notified about questions which has any of these tags" + chr(10)
    msg += "    site - you will be notified about question from this site. Default value: stackoverflow." + chr(10)
    msg += "  examples:" + chr(10)
    msg += "    /add tags=oracle # subscribe for all Oracle related questions from stackoverflow" + chr(10)
    msg += "    /add site=stackoverflow tags=postgresql # subscribe for all Postgresql related questions " \
           "from stackoverflow" + chr(10)
    msg += "    /add site=superuser tags_all=iptables,docker # subscribe for questions from superuser about iptables "\
           "AND docker" + chr(10)
    msg += "    /add site=gaming tags=starcraft-2, tags_exclude=starcraft-protoss # subscribe for questions from " \
           "gaming about starcraft 2, but not about protoss" + chr(10)
    msg += "/list - show active subscriptions" + chr(10)
    msg += "/del - delete subscription. Examples:" + chr(10)
    msg += "  /del 3 - remove third subscription from the list" + chr(10)
    msg += "  /del all - remove all subscriptions" + chr(10)
    msg += "/help - this menu" + chr(10)
    msg += "/sources - link on the bot source code" + chr(10)
    msg += "/other - link on the other my bots"
    context.bot.send_message(text=msg,
                             chat_id=update.effective_chat.id)


def site_list_handler(update: Update, context: CallbackContext):
    global site_list
    global handler_log
    handler_log.info("Received list command from user {}".format(update.effective_chat.id))
    msg = "Stackexchange sites supported: " + chr(10)
    for i in site_list:
        msg += str(i) + "," + chr(10)
        if len(msg) >= 500:
            context.bot.send_message(text=msg,
                                     chat_id=update.effective_chat.id)
            msg = ""
    if len(msg) > 0:
        context.bot.send_message(text=msg,
                                 chat_id=update.effective_chat.id)


def subs_list(update: Update, context: CallbackContext):
    global handler_log
    handler_log.info("Received list command from user {}".format(update.effective_chat.id))
    connect = get_connect()
    cur = connect.cursor()
    cur.execute("""select st.api_site_parameter, row_number() over (order by s.id) rn, tags
                        from stackexchange_db.subscriptions s
                        join stackexchange_db.sites st on st.id = s.site_id where s.telegram_id = %s
                        order by 2 """, (update.effective_chat.id, ))
    msg = "Active subscriptions: " + chr(10)
    for site, rn, tags in cur:
        msg += "№ {}. Site: {}, tags {}".format(rn, site, tags) + chr(10)
        if len(msg) >= 500:
            context.bot.send_message(text=msg,
                                     chat_id=update.effective_chat.id)
            msg = ""
    context.bot.send_message(text=msg,
                             chat_id=update.effective_chat.id)


def admin_stats(update: Update, context: CallbackContext):
    global handler_log
    global config
    if update.effective_chat.id in config.admin_list:
        handler_log.debug("Received admin_stats from user {}".format(update.effective_chat.id))
    else:
        handler_log.critical("Received illegal admin_stats from user {}".format(update.effective_chat.id))
        return
    connect = get_connect()
    cur = connect.cursor()
    cur.execute("""select count(1), st.api_site_parameter
                        from stackexchange_db.subscriptions s
                        join stackexchange_db.sites st
                        on st.id = s.site_id group by st.api_site_parameter""")
    msg = ""
    stats = get_stats()
    for i in stats:
        msg += "{}: {}".format(i, stats[i]) + chr(10)
    for cnt, nm in cur:
        msg += "site: {}, subs: {}".format(nm, cnt) + chr(10)
    context.bot.send_message(text=msg, chat_id=update.effective_chat.id)


def admin_shutdown(update: Update, context: CallbackContext):
    global handler_log
    global config
    global is_running
    if update.effective_chat.id in config.admin_list:
        handler_log.debug("Received admin_shutdown from user {}".format(update.effective_chat.id))
    else:
        handler_log.critical("Received illegal admin_shutdown from user {}".format(update.effective_chat.id))
        return
    is_running = False
    context.bot.send_message(text="Shutdown started", chat_id=update.effective_chat.id)
    context.bot.close()


def delete_sub(update: Update, context: CallbackContext):
    global handler_log
    connect = get_connect()
    cur = connect.cursor()
    cmd = update.message.text[5:]
    handler_log.debug("Received delete cmd for row {} and user{}".format(cmd, update.effective_chat.id))
    if cmd == "all":
        cur.execute("""delete from stackexchange_db.subscriptions s
                 where s.telegram_id = %s
                                """, (update.effective_chat.id,))
        connect.commit()
    else:
        try:
            rn = int(cmd)
        except ValueError as err:
            handler_log.debug("Subscription for row {} and user {} not deleted: {}".format(cmd,
                                                                                           update.effective_chat.id,
                                                                                           err))
            context.bot.send_message(text="Incorrect number",
                                     chat_id=update.effective_chat.id)
            return
        cur.execute("""delete
                       from
                           stackexchange_db.subscriptions s
                       where
                           id = (
                           select
                               sq.id
                           from
                               (
                               select
                                   id,
                                   row_number() over (
                                   order by s.id) rn
                               from
                                   stackexchange_db.subscriptions sb
                               where
                                   s.telegram_id = %s) sq
                           where
                               sq.rn = %s)
                        """, (update.effective_chat.id, rn))
        connect.commit()
    handler_log.debug("Subscription for row {} and user {} deleted".format(cmd, update.effective_chat.id))
    context.bot.send_message(text="Subscription deleted",
                             chat_id=update.effective_chat.id)


def add(update: Update, context: CallbackContext):
    global site_list
    global handler_log
    handler_log.info("Received add command from user {}".format(update.effective_chat.id))
    args = update.message.text.split(' ')
    mode = MODE_EMPTY
    site = "stackoverflow"
    tags = []
    tags_all = []
    tags_exclude = []
    for i in args[1:]:
        if i.startswith("tags="):
            mode = MODE_TAGS
            for j in i[5:].split(","):
                if len(j) > 0:
                    tags.append(j)
        elif i.startswith("tags_any="):
            mode = MODE_TAGS
            for j in i[9:].split(","):
                if len(j) > 0:
                    tags.append(j)
        elif i.startswith("tags_all="):
            mode = MODE_TAGS_ALL
            for j in i[9:].split(","):
                if len(j) > 0:
                    tags_all.append(j)
        elif i.startswith("tags_exclude="):
            mode = MODE_TAGS_EXCLUDE
            for j in i[13:].split(","):
                if len(j) > 0:
                    tags_exclude.append(j)
        elif i.startswith("site="):
            site = i[5:]
        elif len(i) > 0:
            if mode == MODE_TAGS:
                tags.append(i)
            elif mode == MODE_TAGS_ALL:
                tags_all.append(i)
            elif mode == MODE_TAGS_EXCLUDE:
                tags_exclude.append(i)
    if (len(tags) > 0 or len(tags_all) > 0 or len(tags_exclude) > 0) and len(site) > 0:
        tag_base = {"tags_any": tags, "tags_all": tags_all, "tags_exclude": tags_exclude}
        connect = get_connect()
        cur = connect.cursor()
        if site not in site_list:
            cur.execute("select id from stackexchange_db.sites where api_site_parameter = %s", (site,))
            buf = cur.fetchone()
            if buf is None:
                context.bot.send_message(text="Incorrect stackexchange site name: {}".format(site),
                                         chat_id=update.effective_chat.id)
                return
            else:
                site_list[site] = buf[0]
        cur.execute("""
        insert into stackexchange_db.subscriptions(telegram_id, site_id, tags) values (%s, %s, %s)
        """, (update.effective_chat.id, site_list[site], json.dumps(tag_base)))
        connect.commit()
        context.bot.send_message(text="Subscription added",
                                 chat_id=update.effective_chat.id)
    elif len(site) == 0:
        context.bot.send_message(text="Empty site name",
                                 chat_id=update.effective_chat.id)
    else:
        context.bot.send_message(text="Empty all tag lists",
                                 chat_id=update.effective_chat.id)


def echo(update: Update, context: CallbackContext):
    pass


def request_questions(site: str, from_date: int) -> List[Question]:
    global api_log
    res = []
    cnt = 0
    base_url = "https://api.stackexchange.com/2.3/questions/unanswered"
    page = 1
    need_request = True
    while need_request:
        url = "{0}?order=desc&sort=activity&site={1}&fromdate={2}&pagesize={3}&page={4}".format(base_url, site,
                                                                                                from_date,
                                                                                                PAGE_SIZE, page)
        while True:
            api_log.info("Sending request {}".format(base_url))
            try:
                r = requests.get(url, timeout=30)
                if r.status_code == 200:
                    cnt = 0
            except BaseException as err:
                api_log.exception(err)
                api_log.info("Sleep because error")
                time.sleep(5)
                api_log.info("End sleep because error")
                cnt += 1
                if cnt >= MAX_TRIES:
                    break
                continue
            api_log.info("Answer on {} is {}".format(base_url, r.status_code))
            api_log.debug("Full response on {} is {}".format(base_url, r.text))
            if r.status_code == 200 or cnt >= MAX_TRIES:
                break
            if r.status_code in [400, 403]:
                api_log.info("Sleep because {}".format(r.text))
                time.sleep(5)
                api_log.info("End sleep because {}".format(r.text))
            cnt += 1
            time.sleep(WAIT_BETWEEN_TRIES)
        if r.status_code == 200:
            obj = r.json().get("items")
            if cnt >= MAX_TRIES:
                need_request = False
            else:
                need_request = r.json().get("has_more")
            for i in obj:
                res.append(Question(title=i.get("title"), link=i.get("link"), question_id=i.get("question_id"),
                                    creation_date=i.get("creation_date"),
                                    tags=i.get("tags")))
        else:
            api_log.error("Incorrect response {} {} from {}" .format(r.status_code, r.text, url))
            need_request = False
        page += 1
        api_log.info("Need to request more: {}, next page: {}, page size {}".format(need_request, page, PAGE_SIZE))

    return res


def request_sites():
    cnt = 0
    base_url = "https://api.stackexchange.com/2.3/sites"
    url = base_url
    while True:
        r = requests.get(url)
        api_log.info("Answer on {} is {}".format(base_url, r.status_code))
        api_log.debug("Full response on {} is {}".format(base_url, r.text))
        if r.status_code == 200 or cnt >= MAX_TRIES:
            break
        cnt += 1
        time.sleep(WAIT_BETWEEN_TRIES)
    obj = r.json().get("items")

    res = []
    if r.status_code == 200:
        for i in obj:
            res.append(i.get("api_site_parameter"))
    return res


def clear_tags(list_with_q: List) -> List:
    res = []
    for i in list_with_q:
        if i[0] == "'":
            res.append(i[1:len(i) - 1])
        elif i[0] == '"':
            res.append(i[1:len(i) - 1])
        else:
            res.append(i)
    return res


def main():
    global handler_log
    global api_log
    global config
    global is_running
    global site_list
    parser = argparse.ArgumentParser(description='Idle RPG server.')
    parser.add_argument("--config", '-cfg', help="Path to config file", action="store", default="cfg//main.json")
    parser.add_argument("--delay", help="Number seconds app will wait before start", action="store", default=None)
    args = parser.parse_args()
    if args.delay is not None:
        time.sleep(int(args.delay))

    site_list = {}

    config = Config(args.config)
    main_log = get_logger("main_bot", config.log_level, True)
    handler_log = get_logger("handler", config.log_level, True)
    api_log = get_logger("api", config.log_level, True)

    set_connect(config)

    updater = Updater(token=config.secret, use_context=True)
    dispatcher = updater.dispatcher

    start_handler = CommandHandler('start', start)
    add_handler = CommandHandler('add', add)
    sites_handler = CommandHandler('sites', site_list_handler)
    delete_handler = CommandHandler('del', delete_sub)
    subs_list_handler = CommandHandler('list', subs_list)
    other_handler = CommandHandler('other', other_bots)
    help_handler = CommandHandler('help', help_response)
    sources_handler = CommandHandler('sources', sources)
    shutdown_handler = CommandHandler('admin_shutdown', admin_shutdown)
    stats_handler = CommandHandler('admin_stats', admin_stats)
    echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(add_handler)
    dispatcher.add_handler(sites_handler)
    dispatcher.add_handler(subs_list_handler)
    dispatcher.add_handler(delete_handler)
    dispatcher.add_handler(other_handler)
    dispatcher.add_handler(help_handler)
    dispatcher.add_handler(sources_handler)
    dispatcher.add_handler(shutdown_handler)
    dispatcher.add_handler(stats_handler)
    dispatcher.add_handler(echo_handler)

    updater.start_polling()

    is_running = True

    site_request_date = datetime.datetime.now()
    r = request_sites()
    set_sites(r)

    set_startup()
    for i in config.admin_list:
        dispatcher.bot.send_message(text="Bot started", chat_id=i)

    while is_running:
        try:
            if site_request_date + datetime.timedelta(hours=24) <= datetime.datetime.now():
                main_log.info("Renew sites")
                site_request_date = datetime.datetime.now()
                r = request_sites()
                set_sites(r)
            connect = get_connect()
            cur = connect.cursor()
            dt_next_update = datetime.datetime.now() + datetime.timedelta(minutes=15)
            cur.execute("select u.id, u.last_question_id, u.last_question_time, st.api_site_parameter, st.id"
                        "  from stackexchange_db.site_updates u"
                        "  right join stackexchange_db.sites st on st.id = u.site_id"
                        "  where (u.dt_next_update <= statement_timestamp() or u.dt_next_update is null)"
                        "  and exists (select null from stackexchange_db.subscriptions s where s.site_id = st.id)"
                        "  order by u.dt_next_update, st.id")
            statuses = cur.fetchall()
            main_log.info("Found {} sites to check".format(len(statuses)))
            for i in statuses:
                if i[0] is None:
                    cur.execute("""insert into stackexchange_db.site_updates(site_id, dt_next_update)
                    values (%s, statement_timestamp()) returning id""",
                                (i[4],))
                    main_log.info("Saved new update status for site {}".format(i[4],))
                    connect.commit()
                    continue
                msg_cnt = 0
                cur.execute("""update stackexchange_db.site_updates u set update_status_id = 2
                where u.id = %s""",
                            (i[0],))
                connect.commit()
                main_log.info("Started update site with site_id {} update_id {} and name {}".format(i[4], i[0], i[3]))
                if i[2] is None:
                    time_border = int((datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp())
                else:
                    time_border = i[2] - 5
                main_log.info("Time border {}".format(time_border))
                questions = request_questions(i[3], time_border)
                if len(questions) == 0:
                    main_log.info("Empty questions list")
                    cur.execute("""update stackexchange_db.site_updates u set update_status_id = 1, dt_next_update = %s
                                                    where u.id = %s""",
                                (dt_next_update, i[0]))
                    connect.commit()
                    continue
                else:
                    main_log.info("Get {} questions".format(len(questions)))
                cur.execute("""select s.telegram_id, tags from stackexchange_db.subscriptions s where s.site_id = %s
                order by telegram_id""",
                            (i[4],))
                max_question_id = i[1]
                max_question_time = i[2]
                for q in questions:
                    if max_question_id is None or max_question_id < q.question_id:
                        max_question_id = q.question_id
                    if max_question_time is None or max_question_time < q.creation_date:
                        max_question_time = q.creation_date
                while True:
                    subs = cur.fetchmany(size=1000)
                    main_log.info("Fetched {} subscriptions".format(len(subs)))
                    queued_msgs = {}
                    for q in questions:
                        sent = False
                        cur_id = None
                        # skip already proceed questions
                        if i[1] is not None and q.question_id <= i[1]:
                            continue
                        for s in subs:
                            if sent and s[0] == cur_id:
                                main_log.debug(
                                    "Skip check for user {} because question {} is sent ".format(s[0], q.question_id))
                                continue
                            else:
                                cur_id = s[0]
                                sent = False
                            cur_tags = s[1]
                            tags_or = clear_tags(cur_tags.get("tags_any"))
                            tags_and = clear_tags(cur_tags.get("tags_all"))
                            tags_not = clear_tags(cur_tags.get("tags_exclude"))
                            skip = False
                            for e in tags_not:
                                if e in q.tags:
                                    main_log.debug(
                                        "Failed check for question {} with tags {} on exclude tag {} "
                                            .format(q.question_id, q.tags, e))
                                    skip = True
                                    break
                            if skip:
                                continue
                            skip = True
                            for o in tags_or:
                                if o in q.tags:
                                    main_log.debug(
                                        "Succeed check for question {} with tags {} on or tag {} ".format(
                                            q.question_id, q.tags, o))
                                    skip = False
                                    break
                                else:
                                    main_log.debug(
                                        "Check for question {} with tags {} on or tag {} fail ".format(
                                            q.question_id, q.tags, o))
                            if skip:
                                main_log.debug(
                                    "Failed check for question {} with tags {} on or tags {} ".format(
                                        q.question_id, q.tags, tags_or))
                                continue
                            skip = False
                            for a in tags_and:
                                if a not in q.tags:
                                    main_log.debug("Succeed check for question {} with tags {} on and tag {} ".format(
                                        q.question_id, q.tags, a))
                                    skip = True
                                    break
                            if skip:
                                continue
                            if s[0] not in queued_msgs:
                                queued_msgs[s[0]] = []
                            queued_msgs[s[0]].append(q)
                            sent = True
                    main_log.info("Proceed {} subscriptions and {} questions".format(len(subs), len(questions)))
                    for usr in queued_msgs:
                        msg = ""
                        for q in queued_msgs[usr]:
                            buf = "Question: {0}, link: {1}".format(q.title, q.link) + chr(10)
                            if len(msg) + len(buf) >= 4096:
                                msg_cnt += 1
                                dispatcher.bot.send_message(chat_id=usr,
                                                            text=msg)
                                msg = buf
                                if msg_cnt % 30 == 0:
                                    time.sleep(1)
                                    main_log.info("Sent {} messages, sleep".format(msg_cnt))
                            else:
                                msg += buf
                        try:
                            dispatcher.bot.send_message(chat_id=usr,
                                                        text=msg)
                        except Unauthorized as err:
                            main_log.exception(err)
                            main_log.info("Delete subscriptions for user {} because he blocked us ".format(usr))
                            cur.execute("""delete from stackexchange_db.subscriptions where telegram_id = %s""",
                                        (usr,))
                            main_log.info("Deleted subscriptions for user {} ".format(usr))
                            connect.commit()
                        msg_cnt += 1
                        if msg_cnt % 30 == 0:
                            time.sleep(1)
                            main_log.info("Sent {} messages, sleep".format(msg_cnt))
                    main_log.info("Sent {} messages".format(msg_cnt))
                    if len(subs) < 1000:
                        main_log.info("Proceed all".format())
                        break
                cur.execute("""update stackexchange_db.site_updates u set update_status_id = 1, dt_next_update = %s,
                                last_question_id = %s, last_question_time=%s
                                where u.id = %s""",
                            (dt_next_update, max_question_id, max_question_time, i[0]))
            # close transaction, even if no changes (still open and stay in idle)
            connect.commit()

            main_log.info("Sleep...")
            time.sleep(4)

        except psycopg2.Error as err:
            main_log.exception(err)
            if config.supress_errors:
                try:
                    set_connect(config)
                except BaseException as err:
                    main_log.exception(err)
                    time.sleep(5)
            else:
                raise
        except BaseException as err:
            main_log.exception(err)
            if config.supress_errors:
                time.sleep(60)
                try:
                    set_connect(config)
                except BaseException as err:
                    main_log.exception(err)
            else:
                raise
    updater.stop()
    main_log.info("Job finished.")
    exit(0)


if __name__ == "__main__":
    main()
