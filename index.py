# -*- coding: utf-8 -*-

import inspect
import sys
import os
import logging
import datetime
import time

from settings import *
from utils import get_text, create_markup, create_pagination_markup
from db_model import UserMap, Session
from query import Query
from dater import dater, create_calendar

from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from sqlalchemy.orm.exc import NoResultFound

from dwapi import datawiz

import telebot
import flask
import redis
from telebot import types

import matplotlib
matplotlib.use("agg")  # switch to png mode
import matplotlib.pyplot as plt

from openpyxl import load_workbook
import pandas as pd

bot = telebot.TeleBot(TOKEN)
server = flask.Flask('localhost')
r_server = redis.Redis('localhost')
current_shown_dates = {}
time_storage = {}


def sign_in(login, password, chat_id):
    start = time.time()
    session = Session()
    try:
        session.query(UserMap).filter(UserMap.chat_id == chat_id).delete()
        datawiz.DW(login, password)
        new_user = UserMap(chat_id=chat_id,
                           login=login,
                           password=password)
        session.add(new_user)
        session.commit()

        query = Query(chat_id)
        query.set_cache_default()
    except InvalidGrantError:
        return False
    finally:
        session.close()
        end = time.time() - start
        time_storage[inspect.stack()[0][3]] = end
    return True


def check_message(message):
    message_text = message.text.lower()
    if message_text == '/start' or \
                    message_text[:4] == u'вход' or \
                    message_text[:4] == u'вхід' or \
                    message_text == u'выход' or \
                    message_text == u'вихід':
        return False
    return True


def sign_out(chat_id, text):
    start = time.time()
    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, text[u'you_leave'], reply_markup=markup)

    try:
        # clear cache
        r_server.delete(chat_id)
        r_server.delete('category#' + str(chat_id))

        # delete from table
        session = Session()
        user = session.query(UserMap).filter(UserMap.chat_id == chat_id).one()
        session.delete(user)
        session.commit()
        session.close()
    except:
        print('No Result Found')
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


@bot.message_handler(commands=['start'])
def process_start(message):
    start = time.time()
    chat_id = message.chat.id

    message_text = u'Доброго дня! \n'
    message_text += u'Я DWBot. Допоможу Вам знайти відповіді на питання по основних показниках вашого бізнесу. \n\n'
    message_text += u'Вхід <логін> <пароль> - команда для початку роботи \n\n'
    message_text += u'Наші контакти: \n'
    message_text += u'Тел: +38 (050) 337-73-53 \n'
    message_text += u'http://datawiz.io/uk/ \n'

    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, message_text, reply_markup=markup)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


@bot.message_handler(func= lambda m: m.text[:4].lower() == u'вхід' or m.text[:4].lower() == u'вход')
def process_login(message):
    start = time.time()
    chat_id = message.chat.id

    # authentication
    raw_login_pass = message.text.split(' ')
    if len(raw_login_pass) != 3:
        bot.send_message(chat_id, u'Невірний формат вводу. Спробуйте ще раз')
        return

    login = raw_login_pass[1]
    password = raw_login_pass[2]

    if not sign_in(login, password, chat_id):
        bot.send_message(chat_id, u'Невірний логін чи пароль. Спробуйте ще раз')
        return

    # create values for new markup
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
    markup.add(u'🇷🇺 Російська', u'🇺🇦 Українська')

    msg = bot.send_message(chat_id, u'Ласкаво просимо %s! Будь ласка, виберіть мову' % login, reply_markup=markup)
    logging.info(u'ENTER ' + str(chat_id) + u' ' + login)
    bot.register_next_step_handler(msg, process_language)
    save_state(chat_id)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


@bot.message_handler(func= lambda m: m.text.lower() == u'выход' or m.text.lower() == u'вихід')
def process_exit(message):
    start = time.time()
    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    sign_out(chat_id, text)
    logging.info(u'EXIT ' + str(chat_id))
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


@bot.message_handler(commands=['speed_test'])
def speed_test(message):
    chat_id = message.chat.id
    global time_storage
    print('SPEED RESULT')
    for k in time_storage:
        print(k, time_storage[k])

    plt.clf()
    plt.figure(figsize=(20,7), dpi=80)
    plt.plot(range(len(time_storage)), time_storage.values(), '-', color='black')
    plt.xticks(range(len(time_storage)), time_storage.keys(), rotation=90)
    plt.savefig('time_measurement/' + str(chat_id) + '-' + str(datetime.datetime.now()) + '.png', )
    time_storage = {}


def process_language(message):
    start = time.time()
    chat_id = message.chat.id

    if check_message(message) is False:
        return
    if message.text not in [u'🇷🇺 Російська', u'🇺🇦 Українська']:
        # create values for new markup
        markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
        markup.add(u'🇷🇺 Російська', u'🇺🇦 Українська')
        msg = bot.send_message(chat_id, u'Будь ласка, виберіть мову', reply_markup=markup)
        bot.register_next_step_handler(msg, process_language)
        return

    if message.text == u'🇺🇦 Українська':
        r_server.hset(chat_id, 'localization', 'UA')
    else:
        r_server.hset(chat_id, 'localization', 'RU')

    text = get_text(r_server.hget(chat_id, 'localization'))
    r_server.hset(chat_id, 'shops_type', text[u'all_shops_sum'])

    # create new markup, types
    markup = create_markup(text[u'types_values'])
    msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
    bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_type(message):
    start = time.time()
    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    if check_message(message) is False:
        return
    if message.text not in text[u'types_values']:
        # create values for new markup
        markup = create_markup(text[u'types_values'])
        msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
        return

    types_map = {
        text[u'types_values'][0]: 'turnover',
        text[u'types_values'][1]: 'qty',
        text[u'types_values'][2]: 'profit',
        text[u'types_values'][3]: 'receipts_qty'
    }
    # set list of types for query if it is main_factors
    main_factors = text[u'types_values'][4]

    if message.text != main_factors:
        r_server.hset(chat_id, 'type', types_map[message.text])
    else:
        r_server.hset(chat_id, 'type', 'all')

    # reset pages
    r_server.hset(chat_id, 'page_shop', 0)
    r_server.hset(chat_id, 'page_category', 0)

    result_text = text[u'choosen_type'] + u' ' + message.text + u'\n\n'
    result_text += text[u'main_menu']

    to_main_menu(message, result_text)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_main_menu(message):
    start = time.time()
    if check_message(message) is False:
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    query = Query(chat_id)

    if message.text == text[u'shops'] or message.text == text[u'next'] or message.text == text[u'prev']:
        shops = [text[u'all_shops_sum']]
        shops += query.get_shops()

        page = r_server.hget(chat_id, 'page_shop')
        page = int(page)

        markup = create_pagination_markup(shops, text, page_number=page)
        bot.send_message(message.chat.id, text[u'shops_answer'], reply_markup=markup)
        bot.register_next_step_handler(message, process_shop)

    elif message.text == text[u'main_menu_values'][1]:
        categories = [text[u'all_categories']] + query.get_categories()

        page = r_server.hget(chat_id, 'page_category')
        page = int(page)
        markup = create_pagination_markup(categories, text, page_number=page)

        bot.send_message(chat_id, text[u'category_answer'], reply_markup=markup)
        bot.register_next_step_handler(message, process_category)

    elif message.text == text[u'period']:
        markup = create_markup(text[u'period_values'])
        bot.send_message(chat_id, text[u'period_answer'], reply_markup=markup)
        bot.register_next_step_handler(message, process_period)

    elif message.text == text[u'choose_period']:
        process_calendar(message)
        to_main_menu(message)

    elif message.text == text[u'visualization']:
        markup = create_markup(text[u'visualization_values'])
        bot.send_message(chat_id, text[u'visualization_answer'], reply_markup=markup)
        bot.register_next_step_handler(message, process_visualization)

    elif message.text == text[u'reset']:
        query.set_cache_default()

        # to types markup
        markup = create_markup(text[u'types_values'])
        msg = bot.send_message(chat_id, text[u'reseted'], reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)

    elif message.text == text[u'exit']:
        markup = types.ReplyKeyboardRemove()
        bot.send_message(chat_id, text[u'you_leave'], reply_markup=markup)

    # query handler
    elif message.text == text[u'OK']:
        markup = create_markup(text[u'types_values'])

        query.set_info_cache()
        logging.info(query.show_query())
        frame = query.make_query()

        msg_text = create_message(chat_id, frame, query)

        vis_type = r_server.hget(chat_id, 'visualization').decode('utf-8', errors='replace')
        if frame is None:
            vis_type = None
        if vis_type == text['visualization_values'][0]:
            create_visualization(query, frame, text['all_shops'], 'line')
            show_visualization(chat_id)
        if vis_type == text['visualization_values'][1]:
            create_visualization(query, frame, text['all_shops'], 'bar')
            show_visualization(chat_id)
        if vis_type == text['visualization_values'][2]:
            create_excel(query, frame)
            show_excel(chat_id)

        msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
    else:
        bot.send_message(chat_id, text[u'main_menu'])
        bot.register_next_step_handler(message, process_main_menu)
    save_state(chat_id)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_shop(message):
    start = time.time()
    if check_message(message) is False:
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    query = Query(chat_id)

    # pagination
    if message.text == text[u'next']:
        r_server.hincrby(chat_id, 'page_shop', 1)
        process_main_menu(message)
        return

    if message.text == text[u'prev']:
        r_server.hincrby(chat_id, 'page_shop', -1)
        process_main_menu(message)
        return

    # get shop id
    # get dict of shops and inverse it for access by name
    try:
        shops_info = query.dw.get_client_info()['shops']
        shops_info = {value: key for key, value in shops_info.iteritems()}

        r_server.hset(chat_id, 'shops_type', message.text)

        if message.text == text[u'all_shops'] or message.text == text[u'all_shops_sum']:
            r_server.hset(str(message.chat.id), 'shop', 'all')
        else:
            r_server.hset(str(message.chat.id), 'shop', shops_info[message.text])

        shops_text = text[u'shops_choosen'] + u' ' + message.text + u'\n\n'
        shops_text += text[u'main_menu']
        to_main_menu(message, shops_text)
    except KeyError:
        bot.send_message(message.chat.id, text[u'shops_answer'])
        bot.register_next_step_handler(message, process_shop)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_category(message):
    start = time.time()
    if check_message(message) is False:
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    query = Query(chat_id)

    # pagination
    if message.text == text[u'next']:
        r_server.hincrby(chat_id, 'page_category', 1)
        process_main_menu(message)
        return

    if message.text == text[u'prev']:
        r_server.hincrby(chat_id, 'page_category', -1)
        process_main_menu(message)
        return

    try:
        # get category id
        if message.text != text[u'all_categories']:
            r_server.hset(str(chat_id), 'category', query.dw.name2id([message.text]).values()[0])
        else:
            r_server.hset(str(chat_id), 'category', query.dw.get_client_info()['root_category'])

        category_text = text[u'category_choosen'] + u' ' + message.text + u'\n\n'
        category_text += text[u'main_menu']
        to_main_menu(message, category_text)
    except:
        bot.send_message(chat_id, text[u'category_answer'])
        bot.register_next_step_handler(message, process_category)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_period(message):
    start = time.time()
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    try:
        if message.text == text[u'choose_period']:
            process_calendar(message)
        else:
            date_from, date_to = dater(message.text, text, chat_id)

            r_server.hset(chat_id, 'date_from', date_from)
            r_server.hset(chat_id, 'date_to', date_to)

            period_text = text[u'period_choosen_answer'] + u' ' + message.text + u'\n\n'
            period_text += text[u'main_menu']
            to_main_menu(message, period_text)
    except:
        bot.send_message(chat_id, text[u'please_choose_period'])
        bot.register_next_step_handler(message, process_period)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_visualization(message):
    start = time.time()
    if check_message(message) is False:
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    if message.text not in text[u'visualization_values']:
        markup = create_markup(text[u'visualization_values'])
        msg = bot.send_message(chat_id, text[u'visualization_answer'], reply_markup=markup)
        bot.register_next_step_handler(msg, process_visualization)
        return

    r_server.hset(chat_id, 'visualization', message.text)

    vis_text = text[u'visualization_choosen_answer'] + u' ' + message.text + u'\n\n'
    vis_text += text[u'main_menu']
    to_main_menu(message, vis_text)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def process_calendar(message):
    start = time.time()
    if check_message(message) is False:
        return

    chat_id = message.chat.id
    query = Query(chat_id)
    now = query.dw.get_client_info()['date_to']
    text = get_text(r_server.hget(chat_id, 'localization'))

    r_server.hset(chat_id, 'date_from', None)
    r_server.hset(chat_id, 'date_to', None)

    date = (now.year, now.month)
    current_shown_dates[chat_id] = date
    markup = create_calendar(now.year,now.month)
    bot.send_message(message.chat.id, text[u'please_choose_period'], reply_markup=markup)
    save_state(chat_id)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def to_main_menu(message, msg_text=None):
    start = time.time()
    chat_id = message.chat.id

    if msg_text is None:
        msg_text = message.text

    text = get_text(r_server.hget(chat_id, 'localization'))

    markup = create_markup(text[u'main_menu_values'])
    msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_main_menu)
    save_state(chat_id)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def create_message(chat_id, frame, query):
    start = time.time()
    text = get_text(r_server.hget(chat_id, 'localization'))
    if frame is None:
        return text['nothing_to_show']

    date_from = r_server.hget(str(chat_id), 'date_from')
    date_to = r_server.hget(str(chat_id), 'date_to')

    mask = "%Y-%m-%d %H:%M:%S"
    date_from = datetime.datetime.strptime(date_from, mask)
    date_to = datetime.datetime.strptime(date_to, mask)

    message = text['period_nic'] + u': ' + str(date_from.date()) + u' - ' \
              + str(date_to.date()) + u'\n'

    if query.category != query.dw.get_client_info()['root_category']:
        message += text['categories'] + u': ' + query.dw.id2name([query.category]).values()[0] + u'\n'
    message += u'\n'

    # handle list or single element
    df = frame.copy()
    del df['date']
    sr = df.sum()

    shop = r_server.hget(chat_id, 'shop')
    if shop == 'all':
        shop = query.dw.get_client_info()['shops'].keys()
    else:
        shop = int(shop)

    # if handle list as single element (for total info)
    if isinstance(shop, list) and len(shop) > 1:
        message += text[u'all_shops_sum'] + u'\n'
    else:
        message += query.id_shop2name(shop) + u'\n'
    for ind in sr.index.values:
        message += query.type_translate(ind) + u' ' + str(sr[ind]) + u'\n'
    message += u'\n'
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end
    return message


def create_visualization(query, frame, all_shops_text, vis_type='line'):
    start = time.time()
    if vis_type is None:
        return
    if frame is None:
        return

    if len(frame.name) > 1:
        shop_name = all_shops_text
    else:
        shop_name = frame.name[0]

    frame = frame.copy()

    # clear plots
    for col in frame.columns.values:
        plt.figure(col + str(query.chat_id),
                            figsize=(16, 8),
                            dpi=160)
        plt.clf()
    frame = frame.set_index('date')
    columns = frame.columns.values

    path = 'visualization/plots/'
    extension = '.png'

    for col in columns:
        item = frame[col]
        figure = plt.figure(col + str(query.chat_id),
                            figsize=(16,8),
                            dpi=160)
        plt.ylabel(query.type_translate(col))
        ax = figure.gca()
        ax.set_facecolor('#E8E8E8')

        if isinstance(shop_name, int):
            shop_name = query.id_shop2name(shop_name)

        plott = item.plot(label=shop_name, kind=vis_type)
        plott.grid(which='major', axis='x', linewidth=0.75, linestyle='-', color='0.75')
        plott.grid(which='minor', axis='x', linewidth=0.5, linestyle='-', color='0.75')
        plott.grid(which='major', axis='y', linewidth=0.75, linestyle='-', color='0.75')
        plott.grid(which='minor', axis='y', linewidth=0.5, linestyle='-', color='0.75')
        plt.legend(loc='upper left', frameon=False)
        plt.savefig(path + col + str(query.chat_id) + extension)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def create_excel(query, frame):
    start = time.time()
    text = get_text(query.chat_id)
    path = 'visualization/excel/'
    extension = '.xlsx'
    file_path = path + str(query.chat_id) + extension

    if len(frame.name) > 1:
        shop_name = text[u'all_shops_sum']
    else:
        shop_name = frame.name[0]
        shop_name = query.id_shop2name(shop_name)

    frame = frame.copy()

    rename_map = {'turnover': text['types_values'][0],
                'qty': text['types_values'][1],
                'profit': text['types_values'][2],
                'receipts_qty': text['types_values'][3],
                'date': text['period_nic']
                }

    frame = frame.rename(columns=rename_map)

    if os.path.exists(file_path) is True:
        book = load_workbook(file_path)
        writer = pd.ExcelWriter(file_path, engine='openpyxl')
        writer.book = book
        writer.sheets = dict((ws.title, ws) for ws in book.worksheets)
    else:
        writer = pd.ExcelWriter(file_path, engine='openpyxl')

    if isinstance(shop_name, int):
        shop_name = str(shop_name)

    frame.to_excel(writer, shop_name)
    writer.save()

    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end
    return


def show_visualization(chat_id):
    start = time.time()
    type_plot = r_server.hget(chat_id, 'type')
    extension = '.png'

    if type_plot != 'all':
        path = 'visualization/plots/' + type_plot + str(chat_id) + extension
        image = open(path, 'rb')
        bot.send_photo(chat_id, image)
    else:
        for tp in ['turnover', 'profit', 'qty', 'receipts_qty']:
            path = 'visualization/plots/' + tp + str(chat_id) + extension
            image = open(path, 'rb')
            bot.send_photo(chat_id, image)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def show_excel(chat_id):
    start = time.time()
    doc = open('visualization/excel/' + str(chat_id) + '.xlsx')
    bot.send_document(chat_id, doc)
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


@bot.callback_query_handler(func=lambda call: call.data == 'next-month')
def next_month(call):
    chat_id = call.message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        year,month = saved_date
        month+=1
        if month>12:
            month=1
            year+=1
        date = (year,month)
        current_shown_dates[chat_id] = date
        markup= create_calendar(year,month)
        bot.edit_message_text(text['please_choose_period'], call.from_user.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, text="")
    else:
        #Do something to inform of the error
        pass


@bot.callback_query_handler(func=lambda call: call.data == 'previous-month')
def previous_month(call):
    chat_id = call.message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        year,month = saved_date
        month-=1
        if month<1:
            month=12
            year-=1
        date = (year,month)
        current_shown_dates[chat_id] = date
        markup= create_calendar(year,month)
        bot.edit_message_text(text['please_choose_period'], call.from_user.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, text="")
    else:
        pass


@bot.callback_query_handler(func=lambda call: call.data[0:13] == 'calendar-day-')
def get_day(call):
    start = time.time()
    chat_id = call.message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        day = call.data[13:]
        date_choosen = datetime.datetime(int(saved_date[0]),int(saved_date[1]),int(day))

        date_from = r_server.hget(str(chat_id), 'date_from')
        date_to = r_server.hget(str(chat_id), 'date_to')

        if date_from == 'None':
            r_server.hset(str(chat_id), 'date_from', date_choosen)
        elif date_to == 'None':
            date_to = date_choosen

            mask = "%Y-%m-%d %H:%M:%S"
            date_from = datetime.datetime.strptime(date_from, mask)

            if date_from > date_to:
                date_to, date_from = date_from, date_to

            date_to = str(date_to)
            date_from = str(date_from)

            r_server.hset(str(chat_id), 'date_to', date_choosen)
            to_main_menu(call.message, text['choosen_period'] + u': '
                         + date_from[:-8] + u' - '
                         + date_to[:-8])
        else:
            bot.send_message(chat_id, text['calendar_excep'])
        bot.answer_callback_query(call.id, text="")
    else:
        pass
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def load_state():
    start = time.time()
    # get all process functions in module and create dict {string_func, func}
    fset = [obj for name, obj in inspect.getmembers(sys.modules[__name__]) if inspect.isfunction(obj)]
    fset = [obj for obj in fset if 'process' in str(obj)]
    fset_string = [str(obj).split()[1] for obj in fset]
    fdict = {key: value for key, value in zip(fset_string, fset)}

    if r_server.exists('pre_message_subscribers_next_step'):
        pre_message_sub = r_server.hgetall('pre_message_subscribers_next_step')
    else:
        pre_message_sub = {}

    # handle pre_message_sub, transform strings to correct values
    for key in pre_message_sub:
        if isinstance(key, str):
            pre_message_sub[int(key)] = pre_message_sub.pop(key)
            func_string = pre_message_sub[int(key)]
            func_string = func_string.split(' ')[1]
            pre_message_sub[int(key)] = [fdict[func_string]]
    bot.pre_message_subscribers_next_step = pre_message_sub
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def save_state(chat_id):
    start = time.time()
    try:
        value = bot.pre_message_subscribers_next_step[chat_id]

# only one function can be located in pre_message_subscribers_next_step
        if len(value) > 1:
            value = value[0]
            bot.pre_message_subscribers_next_step[chat_id] = [value]

        r_server.hset('pre_message_subscribers_next_step', chat_id, value)
    except KeyError:
        logging.error('Key Error')
    end = time.time() - start
    time_storage[inspect.stack()[0][3]] = end


def show_state(text):
    logging.info(text, bot.pre_message_subscribers_next_step)


def clear_state():
    bot.pre_message_subscribers_next_step = {}
    r_server.delete('pre_message_subscribers_next_step')


def delete_state(chat_id):
    bot.pre_message_subscribers_next_step[chat_id] = []

# clear_state()
load_state()
bot.polling(none_stop=True)