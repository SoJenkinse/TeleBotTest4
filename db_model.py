# -*- coding: utf-8 -*-

from sqlalchemy import Column, String, Integer, Boolean, Date, Time
from sqlalchemy import ForeignKey
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from settings import DB_CONNECTION

Base = declarative_base()
engine = create_engine(DB_CONNECTION)
Session = sessionmaker(bind=engine)


class UserMap(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    login = Column(String)
    password = Column(String)
    lang = Column(String)
    timezone = Column(String)

    def __repr__(self):
        return self.login

    def __str__(self):
        return self.login


class UserState(Base):
    __tablename__ = 'state'

    chat_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    state_fun = Column(String)
    sign_in = Column(Boolean)

    user = relationship("UserMap", back_populates="states")

    def __str__(self):
        return str(self.chat_id) + self.state


class UserAlert(Base):
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    query_type = Column(String)
    shop = Column(String)
    category = Column(String)
    date_from = Column(Date)
    date_to = Column(Date)
    visualization = Column(String)
    alert_date = Column(String)
    alert_time = Column(Time)
    is_active = Column(Boolean, default=False)

    user = relationship("UserMap", back_populates="alerts")

    def __str__(self):
        return str(self.chat_id) + ' ' + self.login + ' ' + self.query_type

UserMap.alerts = relationship("UserAlert", order_by=UserAlert.id, back_populates="user")
UserMap.states = relationship("UserState", order_by=UserState.chat_id, back_populates="user")

if __name__ == '__main__':
    Base.metadata.create_all(engine)