# coding:utf-8

"""
There is date transformation and calendar widget
"""

import datetime
from telebot import types
import calendar
from query import Query


def last_day_of_month(any_day):
    next_month = any_day.replace(day=28) + datetime.timedelta(days=4)
    return next_month - datetime.timedelta(days=next_month.day)


def dater(income_text, text, chat_id):
    query = Query(chat_id)  # TODO: make login pass

    today = query.dw.get_client_info()['date_to']
    if income_text == text['period_values'][0]:
        return today - datetime.timedelta(days=1), today - datetime.timedelta(days=1)
    if income_text == text['period_values'][1]:
        return today - datetime.timedelta(6), today
    if income_text == text['period_values'][2]:
        return today.replace(day=today.day - (today.day % 7)), today
    if income_text == text['period_values'][3]:
        # month count
        month = today.month
        if month < 7:
            month = 12 - month
        else:
            month = month - 6
        return datetime.datetime(2015, month, 1), today
    if income_text == text['period_values'][4]:
        from_month_begin = today.replace(day=1, month=today.month-1)
        return from_month_begin, last_day_of_month(from_month_begin)
    if income_text == text['period_values'][5]:
        return today.replace(day=1), today
    if income_text == text['period_values'][6]:
        info = query.dw.get_client_info()
        return info['date_from'], info['date_to']


def create_calendar(year,month):
    markup = types.InlineKeyboardMarkup()
    #First row - Month and Year
    row=[]
    row.append(types.InlineKeyboardButton(calendar.month_name[month]+" "+str(year),callback_data="ignore"))
    markup.row(*row)
    #Second row - Week Days
    week_days=["M","T","W","R","F","S","U"]
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