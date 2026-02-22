from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, TIMESTAMP, Text, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Аккаунты(Base):
    __tablename__ = 'Аккаунты'

    id_пользователя = Column(Integer, primary_key=True, autoincrement=True)
    Никнейм = Column(String(100), nullable=False, unique=True)
    Почта = Column(String(255), nullable=False, unique=True)
    Пароль = Column(String(255), nullable=False)
    Фото = Column(Text)
    Дата_регистрации = Column(TIMESTAMP)
    is_active = Column(Boolean, default=True)
    reading_goal = Column(Integer, default=12)
    pages_per_day_goal = Column(Integer, default=50)
    last_login = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    # Связи
    вишлист = relationship("Вишлист", back_populates="пользователь")
    сессии_статус = relationship("Сессия_статус", back_populates="пользователь")
    сессии = relationship("Сессии", back_populates="пользователь")
    цитаты = relationship("Цитаты", back_populates="пользователь")


class Авторы(Base):
    __tablename__ = 'Авторы'

    id_автора = Column(Integer, primary_key=True, autoincrement=True)
    Имя = Column(String(100), nullable=False)
    Отчество = Column(String(100))
    Фамилия = Column(String(100))
    created_at = Column(TIMESTAMP)

    # Связи
    труд = relationship("Труд", back_populates="автор")
    серии_автора = relationship("Серии_автора", back_populates="автор")


class Произведения(Base):
    __tablename__ = 'Произведения'

    id_произведения = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(500), nullable=False)
    Описание = Column(Text)
    Количество_страниц = Column(Integer)
    original_language = Column(String(50))
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    # Связи
    труд = relationship("Труд", back_populates="произведение")
    содержание = relationship("Содержание", back_populates="произведение")
    сессии_статус = relationship("Сессия_статус", back_populates="произведение")
    сессии = relationship("Сессии", back_populates="произведение")
    цитаты = relationship("Цитаты", back_populates="произведение")


class Труд(Base):
    __tablename__ = 'Труд'

    id_автора = Column(Integer, ForeignKey('Авторы.id_автора', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(Integer, ForeignKey('Произведения.id_произведения', ondelete='CASCADE'), primary_key=True)
    роль = Column(String(100), primary_key=True, default='автор')
    created_at = Column(TIMESTAMP)

    автор = relationship("Авторы", back_populates="труд")
    произведение = relationship("Произведения", back_populates="труд")


class Типы_книги(Base):
    __tablename__ = 'Типы_книги'

    id_типа = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(100), nullable=False, unique=True)

    книги = relationship("Книги", back_populates="тип_книги")


class Серии_книг(Base):
    __tablename__ = 'Серии_книг'

    id_серии = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(200), nullable=False, unique=True)
    created_at = Column(TIMESTAMP)

    книги_в_серии = relationship("Книга_в_серии", back_populates="серия")


class Книги(Base):
    __tablename__ = 'Книги'

    id_книги = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(500), nullable=False)
    ISBN = Column(String(13), unique=True)
    Количество_страниц = Column(Integer, nullable=False)
    id_типа_книги = Column(Integer, ForeignKey('Типы_книги.id_типа'))
    Язык = Column(String(50), default='Русский')
    Фото_обложки = Column(Text)
    Штрих_код = Column(String(20))
    Серия_книг = Column(Boolean, default=False)
    год_издания = Column(Integer)
    издательство = Column(String(200))
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    тип_книги = relationship("Типы_книги", back_populates="книги")
    книги_в_серии = relationship("Книга_в_серии", back_populates="книга")
    содержание = relationship("Содержание", back_populates="книга")
    вишлист = relationship("Вишлист", back_populates="книга")


class Книга_в_серии(Base):
    __tablename__ = 'Книга_в_серии'

    id_книги = Column(Integer, ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_серии = Column(Integer, ForeignKey('Серии_книг.id_серии', ondelete='CASCADE'), primary_key=True)
    Номер_книги_в_серии = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP)

    книга = relationship("Книги", back_populates="книги_в_серии")
    серия = relationship("Серии_книг", back_populates="книги_в_серии")


class Содержание(Base):
    __tablename__ = 'Содержание'

    id_книги = Column(Integer, ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(Integer, ForeignKey('Произведения.id_произведения', ondelete='CASCADE'), primary_key=True)
    порядок_в_книге = Column(Integer, default=1)
    created_at = Column(TIMESTAMP)

    книга = relationship("Книги", back_populates="содержание")
    произведение = relationship("Произведения", back_populates="содержание")


class Серии(Base):
    __tablename__ = 'Серии'

    id_серии = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(200), nullable=False)
    Количество_книг = Column(Integer, default=0)
    created_at = Column(TIMESTAMP)

    серии_автора = relationship("Серии_автора", back_populates="серия")


class Серии_автора(Base):
    __tablename__ = 'Серии_автора'

    id_автора = Column(Integer, ForeignKey('Авторы.id_автора', ondelete='CASCADE'), primary_key=True)
    id_серии = Column(Integer, ForeignKey('Серии.id_серии', ondelete='CASCADE'), primary_key=True)
    created_at = Column(TIMESTAMP)

    автор = relationship("Авторы", back_populates="серии_автора")
    серия = relationship("Серии", back_populates="серии_автора")


class Вишлист(Base):
    __tablename__ = 'Вишлист'

    id_книги = Column(Integer, ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_пользователя = Column(Integer, ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'), primary_key=True)
    дата_добавления = Column(TIMESTAMP, default='CURRENT_TIMESTAMP')
    приоритет = Column(Integer, default=1)

    книга = relationship("Книги", back_populates="вишлист")
    пользователь = relationship("Аккаунты", back_populates="вишлист")


class Сессия_статус(Base):
    __tablename__ = 'Сессия_статус'

    id_пользователя = Column(Integer, ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(Integer, ForeignKey('Произведения.id_произведения', ondelete='CASCADE'), primary_key=True)
    Рейтинг = Column(Float)
    Статус = Column(String(20))
    Дата_прочтения = Column(TIMESTAMP)
    current_page = Column(Integer, default=0)
    review = Column(Text)
    start_date = Column(TIMESTAMP)
    end_date = Column(TIMESTAMP)
    reading_time_minutes = Column(Integer, default=0)
    created_at = Column(TIMESTAMP)
    updated_at = Column(TIMESTAMP)

    пользователь = relationship("Аккаунты", back_populates="сессии_статус")
    произведение = relationship("Произведения", back_populates="сессии_статус")


class Сессии(Base):
    __tablename__ = 'Сессии'

    id_сессии = Column(Integer, primary_key=True, autoincrement=True)
    id_пользователя = Column(Integer, ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'))
    id_произведения = Column(Integer, ForeignKey('Произведения.id_произведения', ondelete='CASCADE'))
    Дата_начала = Column(TIMESTAMP, nullable=False)
    Дата_окончания = Column(TIMESTAMP)
    Время_начала = Column(TIMESTAMP)
    Время_окончания = Column(TIMESTAMP)
    Начальная_страница = Column(Integer, nullable=False)
    Последняя_страница = Column(Integer)
    duration_minutes = Column(Integer)
    pages_read = Column(Integer)
    notes = Column(Text)
    created_at = Column(TIMESTAMP)

    пользователь = relationship("Аккаунты", back_populates="сессии")
    произведение = relationship("Произведения", back_populates="сессии")
    сессии_цитаты = relationship("Сессия_цитаты", back_populates="сессия")


class Цитаты(Base):
    __tablename__ = 'Цитаты'

    id_цитаты = Column(Integer, primary_key=True, autoincrement=True)
    id_пользователя = Column(Integer, ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'))
    id_произведения = Column(Integer, ForeignKey('Произведения.id_произведения', ondelete='CASCADE'))
    Текст = Column(Text, nullable=False)
    Страница = Column(Integer)
    Дата = Column(TIMESTAMP)
    chapter = Column(String(200))
    is_public = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP)

    пользователь = relationship("Аккаунты", back_populates="цитаты")
    произведение = relationship("Произведения", back_populates="цитаты")
    связь_тэги = relationship("Связь_цитаты_тэги", back_populates="цитата")
    сессии_цитаты = relationship("Сессия_цитаты", back_populates="цитата")


class Тэги(Base):
    __tablename__ = 'Тэги'

    id_тэга = Column(Integer, primary_key=True, autoincrement=True)
    Название = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')
    created_at = Column(TIMESTAMP)

    связь_цитаты = relationship("Связь_цитаты_тэги", back_populates="тэг")


class Связь_цитаты_тэги(Base):
    __tablename__ = 'Связь_цитаты_тэги'

    id_цитаты = Column(Integer, ForeignKey('Цитаты.id_цитаты', ondelete='CASCADE'), primary_key=True)
    id_тэга = Column(Integer, ForeignKey('Тэги.id_тэга', ondelete='CASCADE'), primary_key=True)
    created_at = Column(TIMESTAMP)

    цитата = relationship("Цитаты", back_populates="связь_тэги")
    тэг = relationship("Тэги", back_populates="связь_цитаты")


class Сессия_цитаты(Base):
    __tablename__ = 'Сессия_цитаты'

    id_сессии = Column(Integer, ForeignKey('Сессии.id_сессии', ondelete='CASCADE'), primary_key=True)
    id_цитаты = Column(Integer, ForeignKey('Цитаты.id_цитаты', ondelete='CASCADE'), primary_key=True)
    Время_записи = Column(TIMESTAMP)

    сессия = relationship("Сессии", back_populates="сессии_цитаты")
    цитата = relationship("Цитаты", back_populates="сессии_цитаты")