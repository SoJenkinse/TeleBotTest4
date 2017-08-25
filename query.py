# -*- coding: utf-8 -*-

from datetime import datetime, timedelta
from db_model import UserMap, UserState, Session
from utils import get_text
import logging
import pandas as pd
from settings import r_server

from dwapi import datawiz
from sqlalchemy.orm.exc import NoResultFound

import matplotlib
import numpy as np
matplotlib.use("agg")  # switch to png mode


class Query:
    def __init__(self, chat_id):
        try:
            session = Session()
            login = session.query(UserState).filter(UserState.chat_id == chat_id).one().login
            user = session.query(UserMap).filter(UserMap.login == login).one()
            session.close()

            self.dw = datawiz.DW(user.login, user.password)
            self.chat_id = chat_id

            self.query_type = None
            self.shop = None
            self.category = None
            self.date_from = None
            self.date_to = None
        except NoResultFound:
            logging.error('NoResultFound query')

    def set_info(self, query_type, shop, category, date_from, date_to):
        self.query_type = query_type
        self.shop = shop
        self.category = category
        self.date_from = date_from
        self.date_to = date_to

    def set_cache_default(self):
        self.query_type = 'all'
        self.shop = 'all'
        self.category = self.dw.get_client_info()['root_category']
        self.date_to = self.dw.get_client_info()['date_to']
        self.date_from = self.date_to - timedelta(29)

        r_server.hset(self.chat_id, 'shop', 'all')
        r_server.hset(self.chat_id, 'category', self.category)
        r_server.hset(self.chat_id, 'date_from', self.date_from)
        r_server.hset(self.chat_id, 'date_to', self.date_to)
        r_server.hset(self.chat_id, 'visualization', 'None')

    def set_info_cache(self):
        try:
            self.query_type = r_server.hget(self.chat_id, 'type')
            self.shop = r_server.hget(self.chat_id, 'shop')
            self.category = r_server.hget(self.chat_id, 'category')

            date_from = r_server.hget(self.chat_id, 'date_from')
            date_to = r_server.hget(self.chat_id, 'date_to')

            mask = "%Y-%m-%d %H:%M:%S"
            self.date_from = datetime.strptime(date_from, mask)
            self.date_to = datetime.strptime(date_to, mask)
        except TypeError:
            self.set_cache_default()

    def make_query(self):
        query_type = self.query_type
        if query_type == 'all':
            query_type = ['turnover', 'qty', 'profit', 'receipts_qty']

        shop = self.shop
        if shop == 'all':
            shop = self.get_shops_id()
        else:
            shop = [int(shop)]

        date_from = self.date_from
        date_to = self.date_to
        category = self.category
        category = int(category)

        frame = self.dw.get_categories_sale(by=query_type,
                                           shops=shop,
                                           date_from=date_from,
                                           date_to=date_to,
                                           categories=category,
                                           view_type='raw'
                                           )
        if frame.empty is True:
            return None

        check_frame = frame.sum()
        if isinstance(query_type, list):
            check_type = query_type[0]
        else:
            check_type = query_type

        if check_frame[check_type] == 0 or check_frame[check_type] == np.nan:
            return None

        frame = self.make_percent_query(frame, date_from, date_to, query_type, shop, category, 'one')

        if 'name' in frame.columns:
            del frame['name']
        if 'category' in frame.columns:
            del frame['category']

        if isinstance(shop, list):
            shop_name = 'all_shops'
        else:
            shop_name = shop
        frame.name = shop_name
        return frame

    def make_all_shops_query(self):
        query_type = self.query_type
        if query_type == 'all':
            query_type = ['turnover', 'qty', 'profit', 'receipts_qty']

        date_from = self.date_from
        date_to = self.date_to

        category = self.category
        category = int(category)

        shops = self.dw.get_client_info()['shops'].keys()
        frames = []
        for shop in shops:
            frame = self.dw.get_categories_sale(categories=category,
                                           by=query_type,
                                           shops=shop,
                                           date_from=date_from,
                                           date_to=date_to,
                                           view_type='raw'
                                           )
            if frame.empty is False:
                check_frame = frame.sum()
                if isinstance(query_type, list):
                    check_type = query_type[0]
                else:
                    check_type = query_type

                if check_frame[check_type] == 0 or check_frame[check_type] == np.nan:
                    continue

                frame = self.make_percent_query(frame, date_from, date_to, query_type, shop, category, 'all')
                del frame['category']
                frame['shop_name'] = self.id_shop2name(shop)
                frames.append(frame)

        if len(frames) == 0:
            return None

        mainframe = pd.concat(frames)
        return mainframe

    def make_percent_query(self, frame, date_from, date_to, query_type, shop, category, shops_count='one'):

        frame = frame.copy()
        date_to_diff = date_from - timedelta(1)
        date_from_diff = date_to_diff - timedelta(days=(date_to - date_from).days)
        prev_frame = self.dw.get_categories_sale(by=query_type,
                                           shops=shop,
                                           date_from=date_from_diff,
                                           date_to=date_to_diff,
                                           categories=category,
                                           view_type='raw'
                                           )
        current_frame = frame.copy().sum()
        prev_frame = prev_frame.sum()

        if prev_frame.empty is True:
            result_diff_frame = current_frame.copy()
            result_diff_frame[:] = 0.0
        else:
            del prev_frame['category'], prev_frame['date'], prev_frame['name']
            del current_frame['category'], current_frame['date'], current_frame['name']

            try:
                result_diff_frame = (current_frame / prev_frame)*100 - 100
            except ValueError as e:
                print(str(e))
                result_diff_frame = current_frame.copy()
                result_diff_frame[:] = 0.0

        if shops_count == 'one':
            frame = frame.append(result_diff_frame, ignore_index=True)
        else:
            frame = frame.groupby('date', as_index=False).sum()
            frame = frame.append(result_diff_frame, ignore_index=True)
        frame = frame.rename({frame.index[-1]: 'percent'})
        return frame

    def get_shops(self):
        return sorted(self.dw.get_client_info()['shops'].values())

    def get_shops_id(self):
        return self.dw.get_client_info()['shops'].keys()

    def name_shop2id(self, name):
        shops = self.dw.get_client_info()['shops']
        shops = {int(value): key for key, value in shops.iteritems()}
        return shops[name]

    def id_shop2name(self, id):
        shops = self.dw.get_client_info()['shops']
        return shops[id]

    # get list of categories
    def get_categories(self):
        categories = self.dw.search(query="", by="category", level=2)
        return sorted(categories.values())

    def get_categories_id(self):
        categories = self.dw.search(query="", by="category", level=2)
        return sorted(categories.keys())

    def show_query(self):
        message = '{5} QUERY {0}, {1}, {2}, {3}, {4}'.format(self.query_type,
                                                         self.shop,
                                                         self.category,
                                                         self.date_from,
                                                         self.date_to,
                                                         self.chat_id)
        return message

    def type_translate(self, type_string):
        text = get_text(self.chat_id)
        type_map = {'turnover': text['types_values'][0],
                    'qty': text['types_values'][1],
                    'profit': text['types_values'][2],
                    'receipts_qty': text['types_values'][3],
                    'all': text['types_values'][4]
                    }
        return type_map[type_string]

if __name__ == '__main__':
    pass
