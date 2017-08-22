# -*- coding: utf-8 -*-

import inspect
import sys
import os
import logging
import datetime
import re

from settings import *
from utils import get_text, create_markup, create_linear_markup, create_pagination_markup
from db_model import UserMap, UserState, UserAlert, Session
from query import Query
from dater import dater, create_calendar

from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from sqlalchemy.orm.exc import NoResultFound

from dwapi import datawiz
from telebot import types

import matplotlib
matplotlib.use("agg")  # switch to png mode
import matplotlib.pyplot as plt

from openpyxl import load_workbook
import pandas as pd

current_shown_dates = {}
time_storage = {}


def sign_in(login, password, chat_id):
    session = Session()

    # sign out prev authentication if needed
    try:
        user = session.query(UserMap).filter_by(chat_id=chat_id, sign_in=True).one()
        user.sign_in = False
        session.commit()
    except NoResultFound:
        pass

    try:
        datawiz.DW(login, password)
    except InvalidGrantError:
        return False

    try:
        user = session.query(UserMap).filter(UserMap.login == login).one()
        user.sign_in = True
    except NoResultFound:
        user = UserMap(chat_id=chat_id,
                       login=login,
                       password=password,
                       sign_in=True,
                       timezone='UTC+2')
        session.add(user)
    finally:
        session.commit()
        session.close()
    return True


def check_message(message):
    message_text = message.text.lower()
    if message_text == '/start' or \
                    message_text[:4] == u'вход' or \
                    message_text[:4] == u'вхід' or \
                    message_text == u'выход' or \
                    message_text == u'вихід' or \
                    message_text == '/settings':
        return False
    return True


def sign_out(chat_id, text):
    markup = types.ReplyKeyboardRemove()

    if text is None:
        text = get_text(chat_id, force=True)

    bot.send_message(chat_id, text[u'you_leave'], reply_markup=markup)

    try:
        # sign_in to False
        session = Session()
        login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
        user = session.query(UserMap).filter(UserMap.login == login).one()
        user.sign_in = False
        session.commit()
        session.close()

        # clear cache
        r_server.delete(chat_id)
        r_server.delete('category#' + str(chat_id))
    except NoResultFound:
        print('sign_out NoResultFound')


@bot.message_handler(commands=['start'])
def process_start(message):
    chat_id = message.chat.id
    message_text = u'Доброго дня! \n'
    message_text += u'Я DWBot. Допоможу Вам знайти відповіді на питання по основних показниках вашого бізнесу. \n\n'
    message_text += u'Вхід <логін> <пароль> - команда для початку роботи \n\n'
    message_text += u'Наші контакти: \n'
    message_text += u'Тел: +38 (050) 337-73-53 \n'
    message_text += u'http://datawiz.io/uk/ \n'
    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, message_text, reply_markup=markup)


@bot.message_handler(commands=['settings'])
def process_settings(message):
    try:
        chat_id = message.chat.id

        # check authentication
        session = Session()
        try:
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()

            if user.sign_in is False:
                raise Exception
            session.close()
        except:
            session.close()
            markup = types.ReplyKeyboardRemove()
            bot.send_message(chat_id, u'Для доступу до налаштувань увійдіть в свій профіль', reply_markup=markup)
            process_start(message)
            return

        text = get_text(chat_id)

        values = text[u'settings_values']
        markup = create_linear_markup(values)

        if message.text == '/settings':
            message_string = text[u'choose_parameter']
        else:
            message_string = message.text

        bot.send_message(message.chat.id, message_string, reply_markup=markup)
        bot.register_next_step_handler(message, process_settings_handler)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_handler(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        session = Session()

        alert_text = text[u'settings_values'][0]
        timezone_text = text[u'settings_values'][1]
        language_menu_text = text[u'settings_values'][2]
        back_text = text[u'settings_values'][3]

        add_query_submessage = text[u'add_alert_message'].split(' ')
        add_query_submessage = u' '.join(add_query_submessage[:4])

        delete_alert_text = text[u'delete_alert_message']

        # get all alerts
        if message.text == alert_text or add_query_submessage in message.text or message.text == delete_alert_text:
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()
            values = user.alerts

            type_map = {'turnover': text['types_values'][0],
                        'qty': text['types_values'][1],
                        'profit': text['types_values'][2],
                        'receipts_qty': text['types_values'][3],
                        'all': text['types_values'][4]
                        }

            alert_dates = text['alerts_date_values']

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            for i in range(0, len(values)):
                markup.add(u'№' + str(i+1) + u', ' +
                           alert_dates[values[i].alert_date].lower() + u', ' +
                           str(values[i].alert_time)[:-3] + u', ' +
                           type_map[values[i].query_type].lower())
            markup.add(text[u'alerts_menu_values'][u'add'], text[u'alerts_menu_values'][u'done'])

            if add_query_submessage in message.text or message.text == delete_alert_text:
                bot.send_message(chat_id, message.text, reply_markup=markup)
            else:
                bot.send_message(chat_id, text[u'alert_choose_value'], reply_markup=markup)

            bot.register_next_step_handler(message, process_settings_alert)

        elif message.text == text[u'alerts_menu_second_values'][1]:
            message.text = alert_text
            process_settings_handler(message)

        # add alert to database
        elif message.text == u'query done':
            # maps for localization independence
            alert_dates_reverse = {value: key for key, value in text['alerts_date_values'].items()}
            visualization_map = {
                text['visualization_values'][0]: 'plot',
                text['visualization_values'][1]: 'bar',
                text['visualization_values'][2]: 'excel'
            }

            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            query_type = r_server.hget(chat_id, 'type')
            shop = r_server.hget(chat_id, 'shop')
            category = r_server.hget(chat_id, 'category')
            date_from = r_server.hget(chat_id, 'date_from')
            date_to = r_server.hget(chat_id, 'date_to')

            visualization = r_server.hget(chat_id, 'visualization').decode('utf-8', errors='replace')
            if visualization != 'None':
                visualization = visualization_map[visualization]

            alert_date_string = r_server.hget(chat_id, 'alert_date').decode('utf-8', errors='replace')
            alert_date = alert_dates_reverse[alert_date_string]
            alert_time = r_server.hget(chat_id, 'alert_time')

            # prepare data
            mask = "%Y-%m-%d %H:%M:%S"
            date_from = datetime.datetime.strptime(date_from, mask)
            date_to = datetime.datetime.strptime(date_to, mask)
            alert_time = datetime.datetime.strptime(alert_time, '%H:%M').time()

            get_user_id = session.query(UserMap).filter(UserMap.login == login).one().id
            alert = UserAlert(user_id = get_user_id,
                              query_type=query_type,
                              shop=shop,
                              category=category,
                              date_from=date_from,
                              date_to=date_to,
                              visualization=visualization,
                              alert_date=alert_date,
                              alert_time=alert_time)
            session.add(alert)
            session.commit()

            query = Query(chat_id)
            add_query_message = text[u'add_alert_message'].replace(u'{type}', query.type_translate(query_type))

            if shop == 'all':
                shop_string = text[u'all_shops']
            elif shop == '-1':
                shop_string = text[u'all_shops_sum']
            else:
                shop_string = query.id_shop2name(int(shop))

            add_query_message = add_query_message.replace(u'{shop}', shop_string)

            if int(category) != query.dw.get_client_info()['root_category']:
                category_string = query.dw.id2name([int(category)]).values()[0] + u',\n'
            else:
                category_string = u''

            add_query_message = add_query_message.replace(u'{category}, \n', category_string)

            alert_dates = text['alerts_date_values']
            alert_date_string = alert_dates[alert_date]

            add_query_message = add_query_message.replace(u'{date}', alert_date_string)
            add_query_message = add_query_message.replace(u'{time}', str(alert_time)[:-3])

            message.text = add_query_message
            process_settings_handler(message)

        # delete alert
        elif message.text == text[u'alerts_menu_second_values'][0]:
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()
            alerts = user.alerts
            alert_number = int(r_server.hget(chat_id, 'choosen_alert_num')) - 1
            session.delete(alerts[alert_number])
            session.commit()
            message.text = delete_alert_text
            process_settings_handler(message)

        elif message.text == timezone_text:
            markup = types.ReplyKeyboardMarkup()
            markup.add('UTC+0')
            for i in range(1, 13):
                markup.add('UTC-' + str(i), 'UTC+' + str(i))

            bot.send_message(chat_id, text[u'choose_UTC'], reply_markup=markup)
            bot.register_next_step_handler(message, process_settings_timezone)

        elif message.text == language_menu_text:
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()

            if user.lang == 'ua':
                markup.add(u'🇷🇺 Російська', u'🇺🇦 Українська')
            else:
                markup.add(u'🇷🇺 Русский', u'🇺🇦 Украинский')

            bot.send_message(chat_id, text[u'choose_lang'], reply_markup=markup)
            bot.register_next_step_handler(message, process_settings_language)

        elif message.text == back_text:
            # create new markup, types
            markup = create_markup(text[u'types_values'])
            msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
            bot.register_next_step_handler(msg, process_type)
        else:
            print(message.text)
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_settings_handler)

        session.close()
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_language(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        session = Session()
        login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
        user = session.query(UserMap).filter(UserMap.login == login).one()

        if message.text == u'🇺🇦 Українська' or message.text == u'🇺🇦 Украинский':
            lang = 'ua'
        else:
            lang = 'ru'

        user.lang = lang
        session.commit()
        session.close()

        if message.text == u'🇺🇦 Українська':
            language_text = u'українську'
        elif message.text == u'🇺🇦 Украинский':
            language_text = u'українську'
        elif message.text == u'🇷🇺 Російська':
            language_text = u'русский'
        elif message.text == u'🇷🇺 Русский':
            language_text = u'русский'
        else:
            language_text = u''

        text = get_text(chat_id)
        message.text = text[u'language_changed'] + language_text
        process_settings(message)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_timezone(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        timezones = ['UTC+0']
        for i in range(1, 13):
            timezones += ['UTC-' + str(i), 'UTC+' + str(i)]

        if message.text not in timezones:
            bot.send_message(chat_id, text[u'not_recognized'])
            message.text = text[u'settings_values'][1]
            bot.register_next_step_handler(message, process_settings_timezone)
            return

        session = Session()
        login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
        user = session.query(UserMap).filter(UserMap.login == login).one()
        user.timezone = message.text
        session.commit()
        session.close()

        message.text = text[u'UTC_changed'] + message.text
        process_settings(message)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_alert(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        if u'№' == message.text[0]:
            number = re.match(u'\d+', message.text[1:]).group(0)
            r_server.hset(chat_id, 'choosen_alert_num', number)
            markup = create_markup(text[u'alerts_menu_second_values'], resize_keyboard=True)

            session = Session()
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()
            alerts = user.alerts
            alert_number = int(r_server.hget(chat_id, 'choosen_alert_num')) - 1

            for alert in alerts:
                alert.is_active = False

            alerts[alert_number].is_active = True
            session.commit()
            session.close()

            # add alert number to string
            response_text = text[u'choosen_alert']
            response_text = response_text.split('*')
            response_text = response_text[0] + str(number) + response_text[1]
            bot.send_message(chat_id, response_text, reply_markup=markup)
            bot.register_next_step_handler(message, process_settings_handler)
        elif message.text == text[u'alerts_menu_values'][u'add']:
            # change to settings mode
            r_server.hset(chat_id, u'settings_mode', 1)

            markup = create_markup(text[u'types_values'])
            msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
            bot.register_next_step_handler(msg, process_type)
        elif message.text == text[u'alerts_menu_values'][u'done']:
            process_settings(message)
        else:
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_settings_alert)

        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_date(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        if message.text not in text[u'alerts_date_values'].values():
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_settings_date)
            return

        r_server.hset(chat_id, 'alert_date', message.text)

        msg = bot.send_message(chat_id, text[u'choose_alert_time'])
        bot.register_next_step_handler(msg, process_settings_time)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


def process_settings_time(message):
    if check_message(message) is False:
        return
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        # check time
        if re.match('\d\d:\d\d', message.text) is None \
                or int(message.text[0]) > 2 \
                or (int(message.text[0]) == 2 and int(message.text[1]) > 3) \
                or int(message.text[3]) > 5:
            msg = bot.send_message(chat_id, text[u'choose_alert_time'])
            bot.register_next_step_handler(msg, process_settings_time)
            return

        r_server.hset(chat_id, 'alert_time', message.text)
        message.text = u'query done'
        process_settings_handler(message)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'settings')


@bot.message_handler(func= lambda m: m.text[:4].lower() == u'вхід' or m.text[:4].lower() == u'вход')
def process_login(message):
    try:
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

        text = get_text(chat_id, login=login)
        if text is not None:
            # create new markup, types
            markup = create_markup(text[u'types_values'])
            msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
            bot.register_next_step_handler(msg, process_type)
        else:
            # create values for new markup, languages
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(u'🇷🇺 Російська', u'🇺🇦 Українська')

            msg = bot.send_message(chat_id, u'Ласкаво просимо %s! Будь ласка, виберіть мову' % login, reply_markup=markup)
            logging.info(u'ENTER ' + str(chat_id) + u' ' + login)
            bot.register_next_step_handler(msg, process_language)

        save_state(chat_id, login=login)
        query = Query(chat_id)
        query.set_cache_default()
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'start')


@bot.message_handler(func= lambda m: m.text.lower() == u'выход' or m.text.lower() == u'вихід')
def process_exit(message):
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)
        sign_out(chat_id, text)
        logging.info(u'EXIT ' + str(chat_id))
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'start')


def process_language(message):
    try:
        chat_id = message.chat.id

        if check_message(message) is False:
            return
        if message.text not in [u'🇷🇺 Російська', u'🇺🇦 Українська']:
            # create values for new markup
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, resize_keyboard=True)
            markup.add(u'🇷🇺 Російська', u'🇺🇦 Українська')
            msg = bot.send_message(chat_id, u'Не розпізнано', reply_markup=markup)
            bot.register_next_step_handler(msg, process_language)
            return

        session = Session()
        login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
        user = session.query(UserMap).filter(UserMap.login == login).one()
        if message.text == u'🇺🇦 Українська':
            r_server.hset(chat_id, 'localization', 'UA')
            user.lang = 'ua'
        else:
            r_server.hset(chat_id, 'localization', 'RU')
            user.lang = 'ru'
        session.commit()
        session.close()

        text = get_text(chat_id)
        r_server.hset(chat_id, 'shops_type', text[u'all_shops_sum'])

        # create new markup, types
        markup = create_markup(text[u'types_values'])
        msg = bot.send_message(chat_id, text[u'choose_type:'], reply_markup=markup)
        bot.register_next_step_handler(msg, process_type)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message, 'start')


def process_type(message):
    try:
        chat_id = message.chat.id
        text = get_text(chat_id)

        if check_message(message) is False:
            return
        if message.text not in text[u'types_values']:
            # create values for new markup
            markup = create_markup(text[u'types_values'])
            msg = bot.send_message(chat_id, text[u'not_recognized'], reply_markup=markup)
            bot.register_next_step_handler(msg, process_type)
            return

        query = Query(chat_id)
        query.set_cache_default()

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

        if message.text == text[u'types_values'][4]:
            subtext = text[u'choosen']
        else:
            subtext = text[u'choosen_type']

        result_text = subtext + u' ' + message.text + u'\n'
        result_text += text[u'main_menu']

        to_main_menu(message, result_text)
    except InvalidGrantError as e:
        logging.error(str(e))
        rollback_state(message, 'start')
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_main_menu(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        text = get_text(chat_id)
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
            categories = query.get_categories()

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
            settings_mode = r_server.hget(chat_id, 'settings_mode')
            if settings_mode == '1':
                r_server.hset(chat_id, 'settings_mode', 0)

                markup = create_markup(text[u'alerts_date_values'].values())
                bot.send_message(chat_id, text[u'choose_alert_date'], reply_markup=markup)
                bot.register_next_step_handler(message, process_settings_date)
                return

            markup = create_markup(text[u'types_values'])
            query.set_info_cache()
            logging.info(query.show_query())

            if query.shop == '-1':
                frame = query.make_all_shops_query()
                response_message = create_all_shops_message(frame, query)
            else:
                frame = query.make_query()
                response_message = create_message(chat_id, frame, query)

            if len(response_message) > 1:
                for msg in response_message[:-1]:
                    bot.send_message(chat_id, msg)
                bot.send_message(chat_id, response_message[-1], reply_markup=markup)
            else:
                bot.send_message(chat_id, response_message[0], reply_markup=markup)

            if query.shop == '-1':
                query.shop = 'all'
                frame = query.make_query()

            vis_type = r_server.hget(chat_id, 'visualization').decode('utf-8', errors='replace')
            if frame is None:
                vis_type = None
            if vis_type == text['visualization_values'][0]:
                create_visualization(query, frame, 'line')
                show_visualization(chat_id)
            elif vis_type == text['visualization_values'][1]:
                create_visualization(query, frame, 'bar')
                show_visualization(chat_id)
            elif vis_type == text['visualization_values'][2]:
                create_excel(query, frame)
                show_excel(chat_id)

            bot.register_next_step_handler(message, process_type)
        else:
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_main_menu)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_shop(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        text = get_text(chat_id)
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
                r_server.hset(str(message.chat.id), 'shop', '-1')
            else:
                r_server.hset(str(message.chat.id), 'shop', shops_info[message.text])

            shops_text = text[u'shops_choosen'] + u' ' + message.text + u'\n\n'
            to_main_menu(message, shops_text)
        except KeyError:
            bot.send_message(message.chat.id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_shop)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_category(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        text = get_text(chat_id)
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
                category_dict = query.dw.name2id([message.text])

                if not category_dict:
                    cat_query = message.text + u' '
                    category_dict = query.dw.name2id([cat_query])
                if not category_dict:
                    cat_query = u' ' + message.text
                    category_dict = query.dw.name2id([cat_query])
                r_server.hset(str(chat_id), 'category', category_dict.values()[0])
            else:
                r_server.hset(str(chat_id), 'category', -1)

            category_text = text[u'category_choosen'] + u' ' + message.text + u'\n\n'
            to_main_menu(message, category_text)
        except BaseException as e:
            logging.error(str(chat_id) + ' category_process: ' + str(e))
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_category)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_period(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        text = get_text(chat_id)

        try:
            if message.text == text[u'choose_period']:
                process_calendar(message)
            else:
                date_from, date_to = dater(message.text, text, chat_id)

                r_server.hset(chat_id, 'date_from', date_from)
                r_server.hset(chat_id, 'date_to', date_to)

                period_text = text[u'period_choosen_answer'] + u' ' + message.text + u'\n\n'
                to_main_menu(message, period_text)
        except BaseException as e:
            logging.error(str(e))
            bot.send_message(chat_id, text[u'not_recognized'])
            bot.register_next_step_handler(message, process_period)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_visualization(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        text = get_text(chat_id)

        if message.text not in text[u'visualization_values']:
            markup = create_markup(text[u'visualization_values'])
            msg = bot.send_message(chat_id, text[u'not_recognized'], reply_markup=markup)
            bot.register_next_step_handler(msg, process_visualization)
            return

        r_server.hset(chat_id, 'visualization', message.text)
        vis_text = text[u'visualization_choosen_answer'] + u' ' + message.text.lower() + u'\n\n'
        to_main_menu(message, vis_text)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def process_calendar(message):
    try:
        if check_message(message) is False:
            return

        chat_id = message.chat.id
        query = Query(chat_id)
        now = query.dw.get_client_info()['date_to']
        text = get_text(chat_id)

        r_server.hset(chat_id, 'date_from', None)
        r_server.hset(chat_id, 'date_to', None)

        date = (now.year, now.month)
        current_shown_dates[chat_id] = date

        # specific way to detect localization
        if text[u'type'] == u'Показник':
            markup = create_calendar(now.year,now.month, 'uk_UA.UTF-8')
        else:
            markup = create_calendar(now.year, now.month, 'ru_RU.UTF-8')

        bot.send_message(message.chat.id, text[u'please_choose_period'], reply_markup=markup)
        save_state(chat_id)
    except Exception as e:
        logging.error(str(e))
        rollback_state(message)


def to_main_menu(message, msg_text=None):
    chat_id = message.chat.id
    if msg_text is None:
        msg_text = message.text

    text = get_text(chat_id)

    markup = create_markup(text[u'main_menu_values'])
    msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_main_menu)
    save_state(chat_id)


def to_types_menu(message):
    chat_id = message.chat.id
    text = get_text(chat_id)
    msg_text = message.text
    markup = create_markup(text[u'types_values'])
    msg = bot.send_message(chat_id, msg_text, reply_markup=markup)
    bot.register_next_step_handler(msg, process_type)
    save_state(chat_id)


def create_message(chat_id, frame, query):
    text = get_text(chat_id)
    if frame is None:
        return [text['nothing_to_show']]

    date_from = r_server.hget(str(chat_id), 'date_from')
    date_to = r_server.hget(str(chat_id), 'date_to')

    mask = "%Y-%m-%d %H:%M:%S"
    date_from = datetime.datetime.strptime(date_from, mask)
    date_to = datetime.datetime.strptime(date_to, mask)
    date_str = date_from.date().strftime("%d-%m-%Y")
    if date_from != date_to:
        date_str += u' - ' + date_to.date().strftime("%d-%m-%Y")

    message = text[u'period_nic'] + u': ' + date_str

    # get percent info from frame
    percent = frame[-1:]
    df = frame[:-1].copy()
    if 'date' in df.columns:
        del df['date']
    sr = df.sum()

    shop = r_server.hget(chat_id, 'shop')
    if shop == 'all':
        shop = query.dw.get_client_info()['shops'].keys()
    else:
        shop = int(shop)

    # if handle list as single element (for total info)
    message += u'\n'
    if (isinstance(shop, list) and len(shop) > 1) or shop == -1:
        message += text[u'all_shops_sum'] + u'\n'
    else:
        message += query.id_shop2name(shop) + u'\n'

    if int(query.category) != query.dw.get_client_info()[u'root_category']:
        category_title = query.dw.id2name([query.category]).values()[0]
        message += text[u'categories'] + u': ' + category_title + u'\n'

    if len(sr.index) > 1:
        index_order = ['turnover', 'qty', 'receipts_qty', 'profit']
        sr = sr.reindex(index_order)

    for ind in sr.index.values:
        message += query.type_translate(ind) + u': ' + str(sr[ind]) +\
                   u'  (' + str(percent[ind].iloc[0].round(2)) + u'%)\n'
    message += u'\n'
    return [message]


def create_all_shops_message(frame, query):
    chat_id = query.chat_id
    text = get_text(chat_id)

    if frame is None:
        return [text['nothing_to_show']]

    # get percent
    percent = frame.loc[frame.index == 'percent']
    frame = frame.drop('percent')
    frame = frame.groupby('shop_name').sum()

    if 'name' in frame.columns:
        del frame['name']

    frame = frame.T
    messages = []

    if len(frame.index) > 1:
        for col in frame:
            message = u''
            message += frame[col].name
            specific_percent = percent[percent.shop_name == frame[col].name]
            for ind in ['turnover', 'qty', 'receipts_qty', 'profit']:
                message += u'\n' + query.type_translate(ind) + u': ' + str(frame.get_value(ind, col).round(2)) + \
                           u' (' + str(specific_percent[ind].iloc[0].round(2)) + u'%)'
            messages.append(message)
    else:
        message = u'' + query.type_translate(frame.index[0]) + u'\n'
        for col in frame:
            specific_percent = percent[percent.shop_name == frame[col].name]
            message += frame[col].name + u': ' + str(frame[col][0].round(2)) + u' (' +\
                       str(specific_percent[frame.index[0]].iloc[0].round(2)) + u'%)\n'

        if len(message) > 4096:
            message = message.split(u'\n')
            for i in range(0, len(message), 90):
                messages.append(u'\n'.join(message[i: i + 90]))
        else:
            messages.append(message)

    # add data to first message
    date_from = r_server.hget(str(chat_id), 'date_from')
    date_to = r_server.hget(str(chat_id), 'date_to')

    mask = "%Y-%m-%d %H:%M:%S"
    date_from = datetime.datetime.strptime(date_from, mask)
    date_to = datetime.datetime.strptime(date_to, mask)
    date_str = text['period_nic'] + ': '
    date_str += date_from.date().strftime("%d-%m-%Y")
    if date_from != date_to:
        date_str += u' - ' + date_to.date().strftime("%d-%m-%Y")

    if int(query.category) != query.dw.get_client_info()[u'root_category']:
        category_title = query.dw.id2name([query.category]).values()[0]
        category_str = text['categories'] + ': ' + category_title + u'\n'
    else:
        category_str = u''

    messages[0] = date_str + u'\n' + category_str + messages[0]
    return messages


def create_visualization(query, frame, vis_type='line'):
    if vis_type is None:
        return
    if frame is None:
        return

    if query.shop == '-1':
        del frame['shop_name']
        frame = frame.groupby('date', as_index=False).sum()

    percent = frame[-1:]
    frame = frame[:-1].copy()

    if vis_type == 'bar':
        date_from = r_server.hget(query.chat_id, 'date_from')
        date_to = r_server.hget(query.chat_id, 'date_to')

        mask = "%Y-%m-%d %H:%M:%S"
        date_from = datetime.datetime.strptime(date_from, mask)
        date_to = datetime.datetime.strptime(date_to, mask)

        date_from = date_from.date()
        date_to = date_to.date()

        days_diff = (date_to - date_from).days

        if days_diff > 180:
            changed_df = frame['date'].apply(lambda x: x[:7])
            frame['date'] = changed_df
            frame = frame.groupby(['date']).sum()
            frame.index = frame.index.map(lambda x: x[-2:] + u'-' + x[:4])
        else:
            frame = frame.set_index('date')
            frame.index = frame.index.map(lambda x: x[-2:] + x[4:-2] + x[:4])
    else:
        frame = frame.set_index('date')
        frame.index = frame.index.map(lambda x: x[-2:] + x[4:-2] + x[:4])

    # clear plots
    for col in frame.columns.values:
        plt.figure(col + str(query.chat_id),
                            figsize=(16, 10),
                            dpi=160)
        plt.clf()
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

        for spin in ax.spines.values():
            spin.set_color('#B0B0B0')

        plott = item.plot(label=query.type_translate(col), kind=vis_type)
        plt.title(query.type_translate(col) + u': ' + str(frame[col].sum()) +
                  u' (' + str(percent[col].iloc[0].round(2)) + u'%)')
        plott.grid(which='major', axis='x', linewidth=0.25, linestyle='-', color='0.5')
        plott.grid(which='minor', axis='x', linewidth=0.25, linestyle='-', color='0.5')
        plott.grid(which='major', axis='y', linewidth=0.25, linestyle='-', color='0.5')
        plott.grid(which='minor', axis='y', linewidth=0.25, linestyle='-', color='0.5')

        legend = plt.legend(loc='upper right', frameon=True)
        cut = legend.get_frame()
        cut.set_facecolor('#E8E8E8')

        plt.savefig(path + col + str(query.chat_id) + extension)


def create_excel(query, frame):
    if query.shop == '-1':
        return
    text = get_text(query.chat_id)
    path = 'visualization/excel/'

    session = Session()
    login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
    session.close()

    extension = '.xlsx'
    file_path = path + login + str(query.chat_id) + extension

    if len(frame.name) > 1:
        shop_name = text[u'all_shops_sum']
    else:
        shop_name = frame.name[0]
        shop_name = query.id_shop2name(shop_name)

    frame = frame[:-1].copy()
    frame = frame.append(frame.sum(numeric_only=True), ignore_index=True)
    frame.set_value(len(frame)-1, 'date', frame.iloc[0]['date'] + u' - ' + frame.iloc[len(frame)-2]['date'])

    rename_map = {'turnover': text['types_values'][0],
                'qty': text['types_values'][1],
                'profit': text['types_values'][2],
                'receipts_qty': text['types_values'][3],
                'date': text['period_nic']
                }

    frame = frame.rename(columns=rename_map)
    frame = frame.rename({len(frame)-1: text['total']})

    if isinstance(shop_name, int):
        shop_name = str(shop_name)

    if os.path.exists(file_path) is True:
        book = load_workbook(file_path)
        writer = pd.ExcelWriter(file_path, engine='openpyxl')
        writer.book = book
        writer.sheets = dict((ws.title, ws) for ws in book.worksheets)
        if shop_name in book.get_sheet_names():
            ds = book.get_sheet_by_name(shop_name)
            book.remove_sheet(ds)
            del writer.sheets[shop_name]
    else:
        writer = pd.ExcelWriter(file_path, engine='openpyxl')

    frame.to_excel(writer, shop_name)
    writer.save()
    return


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


def show_excel(chat_id):
    session = Session()
    login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
    session.close()

    doc = open('visualization/excel/' + login + str(chat_id) + '.xlsx')
    bot.send_document(chat_id, doc)


@bot.callback_query_handler(func=lambda call: call.data == 'next-month')
def next_month(call):
    chat_id = call.message.chat.id
    text = get_text(chat_id)

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        year,month = saved_date
        month+=1
        if month>12:
            month=1
            year+=1
        date = (year,month)
        current_shown_dates[chat_id] = date

        # specific way to detect localization
        if text[u'type'] == u'Показник':
            markup = create_calendar(year, month, 'uk_UA.UTF-8')
        else:
            markup = create_calendar(year, month, 'ru_RU.UTF-8')

        bot.edit_message_text(text['please_choose_period'], call.from_user.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, text="")
    else:
        #Do something to inform of the error
        pass


@bot.callback_query_handler(func=lambda call: call.data == 'previous-month')
def previous_month(call):
    chat_id = call.message.chat.id
    text = get_text(chat_id)

    saved_date = current_shown_dates.get(chat_id)
    if saved_date is not None:
        year,month = saved_date
        month-=1
        if month<1:
            month=12
            year-=1
        date = (year,month)
        current_shown_dates[chat_id] = date

        # specific way to detect localization
        if text[u'type'] == u'Показник':
            markup = create_calendar(year, month, 'uk_UA.UTF-8')
        else:
            markup = create_calendar(year, month, 'ru_RU.UTF-8')

        bot.edit_message_text(text['please_choose_period'], call.from_user.id, call.message.message_id, reply_markup=markup)
        bot.answer_callback_query(call.id, text="")
    else:
        pass


@bot.callback_query_handler(func=lambda call: call.data[0:13] == 'calendar-day-')
def get_day(call):
    chat_id = call.message.chat.id
    text = get_text(chat_id)

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
                date_choosen = date_to
                r_server.hset(str(chat_id), 'date_from', date_from)

            date_to = date_to.date().strftime("%d-%m-%Y")
            date_from = date_from.date().strftime("%d-%m-%Y")

            date_str = date_from
            if date_from != date_to:
                date_str += u' - ' + str(date_to)

            r_server.hset(str(chat_id), 'date_to', date_choosen)
            to_main_menu(call.message, text['choosen_period'] + u': ' + date_str)
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

    # create dict from bd values
    session = Session()
    try:
        states = session.query(UserState).all()
        pre_message_sub = {str(obj.chat_id): obj.state_fun for obj in states}
    except NoResultFound:
        pre_message_sub = {}
    finally:
        session.close()

    # handle pre_message_sub, transform strings to correct values
    for key in pre_message_sub:
        if isinstance(key, str):
            pre_message_sub[int(key)] = pre_message_sub.pop(key)
            func_string = pre_message_sub[int(key)]
            func_string = func_string.split(' ')[1]
            pre_message_sub[int(key)] = [fdict[func_string]]
    bot.pre_message_subscribers_next_step = pre_message_sub


def save_state(chat_id, login=None):
    try:
        value = bot.pre_message_subscribers_next_step[chat_id]

        # only one function can be located in pre_message_subscribers_next_step
        if len(value) > 1:
            value = value[0]
            bot.pre_message_subscribers_next_step[chat_id] = [value]

        value = str(value)
        session = Session()
        try:
            state = session.query(UserState).filter(UserState.chat_id == chat_id).one()
            state.state_fun = value

            if login is not None:
                state.login = login

        except NoResultFound:
            if login is not None:
                state = UserState(chat_id=chat_id,
                                  state_fun=value,
                                  login=login)
            else:
                state = UserState(chat_id=chat_id,
                                  state_fun=value)
            session.add(state)
        finally:
            session.commit()
            session.close()
    except KeyError as e:
        logging.error('Key Error, state not saved')
    except Exception as e:
        logging.error(str(e))


def rollback_state(message, rollback_func=None):
    clear_state(message.chat.id)
    if rollback_func == 'start':
        process_start(message)
    elif rollback_func == 'settings':
        process_settings(message)
    else:
        to_types_menu(message)


def show_state(text):
    logging.info(text, bot.pre_message_subscribers_next_step)


def clear_state(chat_id):
    bot.pre_message_subscribers_next_step[chat_id] = []


def clear_states():
    try:
        bot.pre_message_subscribers_next_step = {}
        session = Session()
        session.query(UserState).delete()
        session.commit()
        session.close()
    except Exception as e:
        logging.error('clear_states ' + str(e))

# clear_states()
load_state()
# bot.remove_webhook()
bot.polling(none_stop=True)