# coding:utf-8

"""
There is date transformation and calendar widget
"""

import datetime
from telebot import types
import calendar
from calendar import TimeEncoding, month_name
from query import Query


def last_day_of_month(any_day):
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
    return next_month - datetime.timedelta(days=next_month.day)


def month_name_locale(month_no, locale):
    if locale == 'uk_UA.UTF-8':
        l_month = ['Січень', 'Лютий', 'Березень', 'Квітень',
                   'Травень', 'Червень', 'Липень', 'Серпень',
                   'Вересень', 'Жовтень', 'Листопад', 'Грудень']
        s = l_month[month_no - 1]
        return s
    # for ukrainian
    with TimeEncoding(locale) as encoding:
        s = month_name[month_no]
        if encoding is not None:
            s = s.decode(encoding)
        return s


def dater(income_text, text, chat_id):
    query = Query(chat_id)
    today = query.dw.get_client_info()['date_to']
    if income_text == text['period_values'][0]:
        return today - datetime.timedelta(days=1), today - datetime.timedelta(days=1)
    if income_text == text['period_values'][1]:
        return today - datetime.timedelta(6), today
    if income_text == text['period_values'][2]:
        return today - datetime.timedelta(29), today

    if income_text == text['period_values'][3]:
        prev_week_start = today

        while prev_week_start.strftime('%A') != 'Monday':
            prev_week_start -= datetime.timedelta(days=1)
        return prev_week_start, today

    if income_text == text['period_values'][4]:
        # month count
        day = today.day
        month = today.month
        year = today.year
        if month < 7:
            month = 12 - month
        else:
            month = month - 6
        if month in [4,6,9,11] and day > 31:
            day = 30
        elif year % 4 == 0 and month == 2 and day > 29:
            day = 29
        elif month == 2 and day > 28:
            day = 28
        return datetime.datetime(year, month, day), today
    if income_text == text['period_values'][5]:
        from_month_begin = today.replace(day=1, month=today.month-1)
        return from_month_begin, last_day_of_month(from_month_begin)
    if income_text == text['period_values'][6]:
        return today.replace(day=1), today
    if income_text == text['period_values'][7]:
        info = query.dw.get_client_info()
        return info['date_from'], info['date_to']



def create_calendar(year,month, locale):
    markup = types.InlineKeyboardMarkup()
    #First row - Month and Year
    row=[]
    row.append(types.InlineKeyboardButton(month_name_locale(month, locale) + " " + str(year),callback_data="ignore"))
    markup.row(*row)
    #Second row - Week Days
    if locale == 'uk_UA.UTF-8':
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
    else:
        week_days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    row=[]
    for day in week_days:
        row.append(types.InlineKeyboardButton(day,callback_data="ignore"))
    markup.row(*row)

    my_calendar = calendar.monthcalendar(year, month)
    for week in my_calendar:
        row=[]
        for day in week:
            if(day==0):
                row.append(types.InlineKeyboardButton(" ",callback_data="ignore"))
            else:
                row.append(types.InlineKeyboardButton(str(day),callback_data="calendar-day-"+str(day)))
        markup.row(*row)
    #Last row - Buttons
    row=[]
    row.append(types.InlineKeyboardButton("<",callback_data="previous-month"))
    row.append(types.InlineKeyboardButton(" ",callback_data="ignore"))
    row.append(types.InlineKeyboardButton(">",callback_data="next-month"))
    markup.row(*row)
    return markup