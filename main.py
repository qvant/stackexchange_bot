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

from lib.config import Config
from lib.log import get_logger
from lib.question import Question

MAX_TRIES = 3
WAIT_BETWEEN_TRIES = 3

global conn
global site_list
global handler_log


def set_connect(config: Config):
    global conn
    conn = psycopg2.connect(dbname=config.db_name, user=config.db_user,
                            password=config.db_password, host=config.db_host, port=config.db_port)
    return conn


def get_connect():
    global conn
    return conn


def set_sites(sites):
    global site_list
    connect = get_connect()
    cur = connect.cursor()
    site_list = {}
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
    context.bot.send_message(chat_id=update.effective_chat.id,
                             text="You can may be interested in my other telegram bots: "
                                  " https://t.me/idle_rpg_bot - simple ZPG"
                                  " https://t.me/achievement_hunt_bot - game achievement rarity checker.")

def start(update: Update, context: CallbackContext):
    pass


def site_list_handler(update: Update, context: CallbackContext):
    global site_list
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
    connect = get_connect()
    cur = connect.cursor()
    cur.execute("""select st.api_site_parameter, row_number() over (order by s.id) rn, tags from stackexchange_db.subscriptions s
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


def delete_sub(update: Update, context: CallbackContext):
    global handler_log
    connect = get_connect()
    cur = connect.cursor()
    cmd = update.message.text[5:]
    handler_log.debug("Received delete cmd for row {} and user".format(cmd, update.effective_chat.id))
    if cmd == "all":
        cur.execute("""delete from stackexchange_db.subscriptions s
                 where s.telegram_id = %s
                                """, (update.effective_chat.id,))
        connect.commit()
    else:
        try:
            rn = int(cmd)
        except ValueError as err:
            handler_log.debug("Subscription for row {} and user not deleted: {}".format(cmd, update.effective_chat.id, err))
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
    handler_log.debug("Subscription for row {} and user deleted".format(cmd, update.effective_chat.id))
    context.bot.send_message(text="Success",
                             chat_id=update.effective_chat.id)


def add(update: Update, context: CallbackContext):
    global site_list
    args = update.message.text.split(' ')
    MODE_EMPTY = 0
    MODE_TAGS = 1
    MODE_TAGS_ALL = 2
    MODE_TAGS_EXCLUDE = 2
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
    elif len(site) == 0:
        context.bot.send_message(text="Emptp site name",
                                 chat_id=update.effective_chat.id)
    else:
        context.bot.send_message(text="Empty all tag lists",
                                 chat_id=update.effective_chat.id)


def echo(update: Update, context: CallbackContext):
    pass


def request_questions(site: str, from_date: int) -> List[Question]:
    cnt = 0
    base_url = "https://api.stackexchange.com/2.3/questions/unanswered"
    url = "{0}?order=desc&sort=activity&site={1}&fromdate=".format(base_url, site, from_date)
    while True:
        r = requests.get(url)
        if r.status_code == 200 or cnt >= MAX_TRIES:
            break
        cnt += 1
        time.sleep(WAIT_BETWEEN_TRIES)
    obj = r.json().get("items")
    res = []
    for i in obj:
        res.append(Question(title=i.get("title"), link=i.get("link"), question_id=i.get("question_id"),
                            creation_date=i.get("creation_date"),
                            tags=i.get("tags")))
    return res


def request_sites():
    cnt = 0
    base_url = "https://api.stackexchange.com/2.3/sites"
    url = base_url
    while True:
        r = requests.get(url)
        if r.status_code == 200 or cnt >= MAX_TRIES:
            break
        cnt += 1
        time.sleep(WAIT_BETWEEN_TRIES)
    obj = r.json().get("items")
    res = []
    for i in obj:
        res.append(i.get("api_site_parameter"))
    return res


def clear_tags(list_with_q: List) -> List:
    res = []
    for i in list_with_q:
        if i[0] == "'":
            res.append(i[1:len(i) - 1])
        else:
            res.append(i)
    return res


def main():
    global handler_log
    parser = argparse.ArgumentParser(description='Idle RPG server.')
    parser.add_argument("--config", '-cfg', help="Path to config file", action="store", default="cfg//main.json")
    parser.add_argument("--delay", help="Number seconds app will wait before start", action="store", default=None)
    args = parser.parse_args()
    if args.delay is not None:
        time.sleep(int(args.delay))

    config = Config(args.config)
    main_log = get_logger("main_bot", config.log_level, True)
    handler_log = get_logger("handler", config.log_level, True)

    set_connect(config)

    updater = Updater(token=config.secret, use_context=True)
    dispatcher = updater.dispatcher

    start_handler = CommandHandler('start', start)
    add_handler = CommandHandler('add', add)
    sites_handler = CommandHandler('sites', site_list_handler)
    delete_handler = CommandHandler('del', delete_sub)
    subs_list_handler = CommandHandler('list', subs_list)
    other_handler = CommandHandler('other', other_bots)
    echo_handler = MessageHandler(Filters.text & (~Filters.command), echo)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(add_handler)
    dispatcher.add_handler(sites_handler)
    dispatcher.add_handler(subs_list_handler)
    dispatcher.add_handler(delete_handler)
    dispatcher.add_handler(other_handler)
    dispatcher.add_handler(echo_handler)

    updater.start_polling()

    is_running = True

    r = request_sites()
    set_sites(r)

    while is_running:
        try:
            connect = get_connect()
            cur = connect.cursor()
            dt_next_update = datetime.datetime.now() + datetime.timedelta(minutes=5)
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
                main_log.info("Started update site {} {}".format(i[4], i[0]))
                if i[2] is None:
                    time_border = int((datetime.datetime.now() - datetime.timedelta(hours=1)).timestamp())
                else:
                    time_border = i[2] - 5000
                main_log.info("Time border {}".format(time_border))
                questions = request_questions(i[3], time_border)
                main_log.info("Get {} questions".format(len(questions)))
                cur.execute("""select s.telegram_id, tags from stackexchange_db.subscriptions s where s.site_id = %s
                order by telegram_id""",
                            (i[4],))
                max_question_id = None
                max_question_time = None
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
                        if q.question_id < i[0]:
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
                    main_log.info("Proceed {} subscriptions".format(len(subs)))
                    for usr in queued_msgs:
                        msg = "!"
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
                        dispatcher.bot.send_message(chat_id=usr,
                                                    text=msg)
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
                connect.commit()

            main_log.info("Sleep...")
            time.sleep(4)

        except BaseException as err:
            main_log.critical(err)
            if config.supress_errors:
                pass
            else:
                raise
    updater.stop()
    main_log.info("Job finished.")
    exit(0)


if __name__ == "__main__":
    main()