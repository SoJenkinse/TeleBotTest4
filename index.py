# -*- coding: utf-8 -*-

import inspect
import sys
import logging
import datetime

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

bot = telebot.TeleBot(TOKEN)
server = flask.Flask('localhost')
r_server = redis.Redis('localhost')
current_shown_dates = {}


def sign_in(login, password, chat_id):
    session = Session()
    try:
        # delete before new action
        # TODO: Does it need to delete user before new sign in?
        session.query(UserMap).filter(UserMap.chat_id == chat_id).delete()
        datawiz.DW(login, password)
        new_user = UserMap(chat_id=chat_id,
                           login=login,
                           password=password)
        session.add(new_user)
        session.commit()
    except InvalidGrantError:
        return False
    finally:
        session.close()
    return True


@bot.message_handler(commands=['exit'])
def sign_out(chat_id):
    try:
        # clear cache
        r_server.delete(chat_id)
        r_server.delete('category#' + str(chat_id))
        # delete from table
        # session = Session()
        # user = session.query(UserMap).filter(UserMap.chat_id == chat_id).one()
        # session.delete(user)
        # session.commit()
        # session.close()

    except NoResultFound:
        bot.send_message(chat_id, u'Вы вышли из аккаута')


@bot.message_handler(commands=['start'])
def process_start(message):
    chat_id = message.chat.id

    message_text = u'Добрый день! \n'
    message_text += u'Я DWBot. Помогу вам найти ответы по основным показателям вашего бизнеса. \n\n'
    message_text += u'Вход <логин> <пароль> - команда для начала работы \n\n'
    message_text += u'Наши контакты: \n'
    message_text += u'Тел: +38 (050) 337-73-53 \n'
    message_text += u'http://datawiz.io/uk/ \n'

    bot.send_message(chat_id, message_text)


@bot.message_handler(func= lambda m: m.text[:4] == u'Вход')
def process_login(message):
    chat_id = message.chat.id

    # authentication
    raw_login_pass = message.text.split(' ')
    if len(raw_login_pass) != 3:
        bot.send_message(chat_id, u'Некоректный ввод. Попробуйте еще раз')
        return

    login = raw_login_pass[1]
    password = raw_login_pass[2]

    if not sign_in(login, password, chat_id):
        bot.send_message(chat_id, u'Неверный логин или пароль. Попробуйте еще раз')
        return

    r_server.delete('category#' + str(chat_id))

    # create values for new markup
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    markup.add(u'Русский', u'Украинский')

    msg = bot.send_message(chat_id, u'Добро пожаловать! Выберите язык', reply_markup=markup)
    bot.register_next_step_handler(msg, process_language)
    save_state(chat_id)


def process_language(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id

    if message.text == u'Украинский':
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


def process_type(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

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

    to_main_menu(message, text[u"main_menu"])


def process_main_menu(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    query = Query(chat_id)

    if message.text == text[u'shops']:
        shops = [text[u'all_shops_sum']]
        shops += query.get_shops()

        page = r_server.hget(chat_id, 'page_shop')
        print(page)
        page = int(page)
        markup = create_pagination_markup(shops, text, page_number=page)

        bot.send_message(message.chat.id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_shop)

    if message.text == text[u'categories']:
        # set cache if needed
        if r_server.exists('category#' + str(message.chat.id)) is False:
            bot.send_message(message.chat.id, text[u'wait_please'])
            categories = query.dw.get_category()
            for elem in categories:
                if elem[u'category_level'] == 2:
                    r_server.lpush('category#' + str(message.chat.id), elem[u'category_name'])

        categories = [text[u'all_categories']] + query.get_categories()
        markup = create_markup(categories)
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_category)

    if message.text == text[u'period']:
        markup = create_markup(text[u'period_values'])
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_period)

    if message.text == text[u'choose_period']:
        process_calendar(message)
        to_main_menu(message)

    if message.text == text[u'visualization']:
        markup = create_markup(text[u'visualization_values'])
        bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(message, process_visualization)

    if message.text == text[u'reset']:
        reset_cache_query(chat_id)

        # to types markup
        markup = create_markup(text[u'types_values'])
        msg = bot.send_message(chat_id, message.text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)

    if message.text == text[u'exit']:
        markup = types.ReplyKeyboardRemove()
        bot.send_message(chat_id, text[u'you_leave'], reply_markup=markup)

    # query handler
    if message.text == text[u'OK']:
        markup = create_markup(text[u'types_values'])

        query.set_info_cache()
        query.show_query()
        frame = query.make_query()

        msg_text = create_message(chat_id, frame)

        vis_type = r_server.hget(chat_id, 'visualization').decode('utf-8', errors='replace')
        print(type(vis_type), vis_type)
        if vis_type == text['visualization_values'][0]:
            create_visualization(chat_id, frame, 'line')
            show_visualization(chat_id)
        if vis_type == text['visualization_values'][1]:
            create_visualization(chat_id, frame, 'bar')
            show_visualization(chat_id)
        if vis_type == text['visualization_values'][2]:
            pass

        print('msg text', msg_text)
        msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)


def process_shop(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
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
    shops_info = query.dw.get_client_info()['shops']
    shops_info = {value: key for key, value in shops_info.iteritems()}

    r_server.hset(chat_id, 'shops_type', message.text)

    if message.text == text[u'all_shops'] or message.text == text[u'all_shops_sum']:
        r_server.hset(str(message.chat.id), 'shop', 'all')
    else:
        r_server.hset(str(message.chat.id), 'shop', shops_info[message.text])
    to_main_menu(message)


def process_category(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))
    query = Query(chat_id)

    # get category id
    if message.text != text[u'all_categories']:
        r_server.hset(str(chat_id), 'category', query.dw.name2id([message.text]).values()[0])
    else:
        r_server.hset(str(chat_id), 'category', query.dw.get_client_info()['root_category'])
    to_main_menu(message)


def process_period(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    if message.text == text[u'choose_period']:
        process_calendar(message)
    else:
        date_from, date_to = dater(message.text, text, chat_id)

        r_server.hset(chat_id, 'date_from', date_from)
        r_server.hset(chat_id, 'date_to', date_to)

        to_main_menu(message)


def process_visualization(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
        return

    chat_id = message.chat.id
    r_server.hset(chat_id, 'visualization', message.text)
    to_main_menu(message)


def process_calendar(message):
    if message.text == '/start' or message.text[:4] == u'Вход':
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


def to_main_menu(message, msg_text=None):
    chat_id = message.chat.id

    if msg_text is None:
        msg_text = message.text

    text = get_text(r_server.hget(chat_id, 'localization'))

    markup = create_markup(text[u'main_menu_values'])
    msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_main_menu)
    save_state(chat_id)


def create_message(chat_id, frame):
    query = Query(chat_id)
    text = get_text(r_server.hget(chat_id, 'localization'))
    if frame is None:
        return text['nothing_to_show']

    date_from = r_server.hget(str(chat_id), 'date_from')
    date_to = r_server.hget(str(chat_id), 'date_to')

    mask = "%Y-%m-%d %H:%M:%S"
    date_from = datetime.datetime.strptime(date_from, mask)
    date_to = datetime.datetime.strptime(date_to, mask)

    message = text['period'] + u': ' + str(date_from.date()) + u' - ' \
              + str(date_to.date()) + u'\n'

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
    return message


def create_visualization(chat_id, frame, vis_type='line'):
    query = Query(chat_id)
    if vis_type is None:
        return

    frame = frame.copy()

    # clear plots
    for col in frame.columns.values:
        plt.figure(col + str(chat_id),
                            figsize=(16, 8),
                            dpi=160)
        plt.clf()
    shop_name = 'shop'  # TODO: shop names
    frame = frame.set_index('date')
    columns = frame.columns.values

    path = 'visualization/plots/'
    extension = '.png'

    for col in columns:
        item = frame[col]
        figure = plt.figure(col + str(chat_id),
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
        plt.savefig(path + col + str(chat_id) + extension)


def show_visualization(chat_id):
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


def reset_cache_query(chat_id):
    query = Query(chat_id)

    r_server.hset(chat_id, 'type', query.query_type)
    r_server.hset(chat_id, 'shop', query.shop)
    r_server.hset(chat_id, 'category', query.category)

    r_server.hset(chat_id, 'date_from', query.date_from)
    r_server.hset(chat_id, 'date_to', query.date_to)
    r_server.hset(chat_id, 'visualization', 'NonVis')


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
    chat_id = call.message.chat.id
    text = get_text(r_server.hget(chat_id, 'localization'))

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        day = call.data[13:]
        date_choosen = datetime.datetime(int(saved_date[0]),int(saved_date[1]),int(day))

        date_from = r_server.hget(str(chat_id), 'date_from')
        date_to = r_server.hget(str(chat_id), 'date_to')

        if date_from == 'None':
            date_from = str(date_choosen)
            r_server.hset(str(chat_id), 'date_from', date_choosen)
        elif date_to == 'None':
            date_to = str(date_choosen)
            r_server.hset(str(chat_id), 'date_to', date_choosen)
            print(date_from, date_to)
            to_main_menu(call.message, text['choosen_period'] + u': '
                         + date_from[:-8] + u' - '
                         + date_to[:-8])
        else:
            bot.send_message(chat_id, text['calendar_excep'])
        bot.answer_callback_query(call.id, text="")
    else:
        pass


def load_state():
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
#    show_state('LOAD')


def save_state(chat_id):
    try:
        value = bot.pre_message_subscribers_next_step[chat_id]
    except KeyError:
        logging.error('Key Error')
        return

    # only one function can be located in pre_message_subscribers_next_step
    if len(value) > 1:
        value = value[0]
        bot.pre_message_subscribers_next_step[chat_id] = [value]

    r_server.hset('pre_message_subscribers_next_step', chat_id, value)


def show_state(text):
    print(text, bot.pre_message_subscribers_next_step)


def clear_state():
    bot.pre_message_subscribers_next_step = {}
    r_server.delete('pre_message_subscribers_next_step')


def delete_state(chat_id):
    bot.pre_message_subscribers_next_step[chat_id] = []
# clear_state()
load_state()
bot.polling(none_stop=True)