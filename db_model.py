from sqlalchemy import Column, String, Integer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from settings import DB_CONNECTION

Base = declarative_base()
engine = create_engine(DB_CONNECTION)
Session = sessionmaker(bind=engine)


class UserMap(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    login = Column(String)
    password = Column(String)

    def __repr__(self):
        return self.login

    def __str__(self):
        return self.login


if __name__ == '__main__':
    session = Session()
    new_user = UserMap(login='test',
                       password='qwerty',
                       chat_id=2)
    session.add(new_user)
    session.commit()