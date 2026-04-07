from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, TIMESTAMP, Text, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import Column, String, Integer, Float, Boolean, ForeignKey, TIMESTAMP, Text, BigInteger, LargeBinary

Base = declarative_base()


class Аккаунты(Base):
    __tablename__ = 'Аккаунты'

    id_пользователя = Column(String(50), primary_key=True)
    Никнейм = Column(String(100), nullable=False, unique=True)
    Почта = Column(String(255), nullable=False, unique=True)
    Пароль = Column(String(255), nullable=False)
    Фото = Column(Text)
    Дата_регистрации = Column(String(50))
    is_active = Column(Boolean, default=True)
    reading_goal = Column(Integer, default=12)
    pages_per_day_goal = Column(Integer, default=50)
    last_login = Column(TIMESTAMP)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    # Связи
    вишлист = relationship("Вишлист", back_populates="пользователь", overlaps="пользователь")
    сессии_статус = relationship("Сессия_статус", back_populates="пользователь", overlaps="пользователь")
    сессии = relationship("Сессии", back_populates="пользователь", overlaps="пользователь")
    цитаты = relationship("Цитаты", back_populates="пользователь", overlaps="пользователь")


class Авторы(Base):
    __tablename__ = 'Авторы'

    id_автора = Column(String(50), primary_key=True)
    Имя = Column(String(100), nullable=False)
    Отчество = Column(String(100))
    Фамилия = Column(String(100))
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    # Связи
    труд = relationship("Труд", back_populates="автор", overlaps="автор")
    серии_автора = relationship("Серии_автора", back_populates="автор", overlaps="автор")


class Произведения(Base):
    __tablename__ = 'Произведения'

    id_произведения = Column(String(50), primary_key=True)
    Название = Column(String(500), nullable=False)
    Описание = Column(Text)
    Количество_страниц = Column(Integer)
    original_language = Column(String(50))
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    # Связи
    труд = relationship("Труд", back_populates="произведение", overlaps="произведение")
    содержание = relationship("Содержание", back_populates="произведение", overlaps="произведение")
    сессии_статус = relationship("Сессия_статус", back_populates="произведение", overlaps="произведение")
    цитаты = relationship("Цитаты", back_populates="произведение", overlaps="произведение")


class Труд(Base):
    __tablename__ = 'Труд'

    id_автора = Column(String(50), ForeignKey('Авторы.id_автора', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(String(50), ForeignKey('Произведения.id_произведения', ondelete='CASCADE'),
                             primary_key=True)
    роль = Column(String(100), primary_key=True, default='автор')
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    автор = relationship("Авторы", back_populates="труд", overlaps="автор")
    произведение = relationship("Произведения", back_populates="труд", overlaps="произведение")


class Типы_книги(Base):
    __tablename__ = 'Типы_книги'

    id_типа = Column(String(50), primary_key=True)
    Название = Column(String(100), nullable=False, unique=True)

    книги = relationship("Книги", back_populates="тип_книги", overlaps="книги")


class Серии_книг(Base):
    __tablename__ = 'Серии_книг'

    id_серии = Column(String(50), primary_key=True)
    Название = Column(String(200), nullable=False, unique=True)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    книги_в_серии = relationship("Книга_в_серии", back_populates="серия", overlaps="серия")


class Книги(Base):
    __tablename__ = 'Книги'

    id_книги = Column(String(50), primary_key=True)
    Название = Column(String(500), nullable=False)
    Автор = Column(String(255), nullable=False)
    ISBN = Column(String(13), unique=True)
    Количество_страниц = Column(Integer, nullable=False)
    id_типа_книги = Column(String(50), ForeignKey('Типы_книги.id_типа'))
    Язык = Column(String(50), default='Русский')
    Фото_обложки = Column(Text)  # Ссылка на Яндекс.Диск (опционально)
    Фото_данные = Column(LargeBinary)  # 👈 НОВОЕ: бинарные данные обложки
    Фото_тип = Column(String(50))  # 👈 НОВОЕ: тип файла (image/jpeg и т.д.)
    Описание = Column(Text)
    Жанр = Column(String(100), default='')
    Штрих_код = Column(String(20))
    Серия_книг = Column(Boolean, default=False)
    год_издания = Column(String(20))
    издательство = Column(String(200))
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    тип_книги = relationship("Типы_книги", back_populates="книги", overlaps="книги")
    книги_в_серии = relationship("Книга_в_серии", back_populates="книга", overlaps="книга")
    содержание = relationship("Содержание", back_populates="книга", overlaps="книга")
    вишлист = relationship("Вишлист", back_populates="книга", overlaps="книга")
    сессии = relationship("Сессии", back_populates="книга", foreign_keys="[Сессии.id_книги]")


class Книга_в_серии(Base):
    __tablename__ = 'Книга_в_серии'

    id_книги = Column(String(50), ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_серии = Column(String(50), ForeignKey('Серии_книг.id_серии', ondelete='CASCADE'), primary_key=True)
    Номер_книги_в_серии = Column(Integer, nullable=False)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    книга = relationship("Книги", back_populates="книги_в_серии", overlaps="книги")
    серия = relationship("Серии_книг", back_populates="книги_в_серии", overlaps="серия")


class Содержание(Base):
    __tablename__ = 'Содержание'

    id_книги = Column(String(50), ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(String(50), ForeignKey('Произведения.id_произведения', ondelete='CASCADE'),
                             primary_key=True)
    порядок_в_книге = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    книга = relationship("Книги", back_populates="содержание", overlaps="книги")
    произведение = relationship("Произведения", back_populates="содержание", overlaps="произведение")


class Серии(Base):
    __tablename__ = 'Серии'

    id_серии = Column(String(50), primary_key=True)
    Название = Column(String(200), nullable=False)
    Количество_книг = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    серии_автора = relationship("Серии_автора", back_populates="серия", overlaps="серия")


class Серии_автора(Base):
    __tablename__ = 'Серии_автора'

    id_автора = Column(String(50), ForeignKey('Авторы.id_автора', ondelete='CASCADE'), primary_key=True)
    id_серии = Column(String(50), ForeignKey('Серии.id_серии', ondelete='CASCADE'), primary_key=True)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    автор = relationship("Авторы", back_populates="серии_автора", overlaps="автор")
    серия = relationship("Серии", back_populates="серии_автора", overlaps="серия")


class Вишлист(Base):
    __tablename__ = 'Вишлист'

    id_книги = Column(String(50), ForeignKey('Книги.id_книги', ondelete='CASCADE'), primary_key=True)
    id_пользователя = Column(String(50), ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'), primary_key=True)
    дата_добавления = Column(String(50))
    приоритет = Column(Integer, default=1)

    книга = relationship("Книги", back_populates="вишлист", overlaps="книги")
    пользователь = relationship("Аккаунты", back_populates="вишлист", overlaps="пользователь")


class Сессия_статус(Base):
    __tablename__ = 'Сессия_статус'

    id_пользователя = Column(String(50), ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'), primary_key=True)
    id_произведения = Column(String(50), ForeignKey('Произведения.id_произведения', ondelete='CASCADE'),
                             primary_key=True)
    Рейтинг = Column(Float, default=0.0)
    Статус = Column(String(20))
    Дата_прочтения = Column(String(50))
    current_page = Column(Integer, default=0)
    review = Column(Text, default='')
    start_date = Column(String(50))
    end_date = Column(String(50))
    added_date = Column(String(50))
    reading_time_minutes = Column(Integer, default=0)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    пользователь = relationship("Аккаунты", back_populates="сессии_статус", overlaps="пользователь")
    произведение = relationship("Произведения", back_populates="сессии_статус", overlaps="произведение")


class Сессии(Base):
    __tablename__ = 'Сессии'

    id_сессии = Column(String(50), primary_key=True)
    id_пользователя = Column(String(50), ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'))
    id_книги = Column(String(50), ForeignKey('Книги.id_книги', ondelete='CASCADE'))  # Прямая связь с книгами
    start_time = Column(BigInteger, default=0)
    end_time = Column(BigInteger, default=0)
    pages_read = Column(Integer, default=0)
    duration_minutes = Column(Integer, default=0)
    Дата_начала = Column(String(50))
    Дата_окончания = Column(String(50))
    Время_начала = Column(String(50))
    Время_окончания = Column(String(50))
    Начальная_страница = Column(Integer, default=0)
    Последняя_страница = Column(Integer)
    notes = Column(Text)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    пользователь = relationship("Аккаунты", back_populates="сессии", overlaps="пользователь")
    книга = relationship("Книги", back_populates="сессии", foreign_keys=[id_книги])
    сессии_цитаты = relationship("Сессия_цитаты", back_populates="сессия", overlaps="сессия")


class Цитаты(Base):
    __tablename__ = 'Цитаты'

    id_цитаты = Column(String(50), primary_key=True)
    id_пользователя = Column(String(50), ForeignKey('Аккаунты.id_пользователя', ondelete='CASCADE'))
    id_произведения = Column(String(50), ForeignKey('Произведения.id_произведения', ondelete='CASCADE'))
    Текст = Column(Text, nullable=False)
    Страница = Column(Integer)
    Дата = Column(String(50))
    chapter = Column(String(200))
    is_public = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    пользователь = relationship("Аккаунты", back_populates="цитаты", overlaps="пользователь")
    произведение = relationship("Произведения", back_populates="цитаты", overlaps="произведение")
    связь_тэги = relationship("Связь_цитаты_тэги", back_populates="цитата", overlaps="цитата")
    сессии_цитаты = relationship("Сессия_цитаты", back_populates="цитата", overlaps="цитата")


class Тэги(Base):
    __tablename__ = 'Тэги'

    id_тэга = Column(String(50), primary_key=True)
    Название = Column(String(100), nullable=False, unique=True)
    color = Column(String(7), default='#3498db')
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    связь_цитаты = relationship("Связь_цитаты_тэги", back_populates="тэг", overlaps="тэг")


class Связь_цитаты_тэги(Base):
    __tablename__ = 'Связь_цитаты_тэги'

    id_цитаты = Column(String(50), ForeignKey('Цитаты.id_цитаты', ondelete='CASCADE'), primary_key=True)
    id_тэга = Column(String(50), ForeignKey('Тэги.id_тэга', ondelete='CASCADE'), primary_key=True)
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    цитата = relationship("Цитаты", back_populates="связь_тэги", overlaps="цитата")
    тэг = relationship("Тэги", back_populates="связь_цитаты", overlaps="тэг")


class Сессия_цитаты(Base):
    __tablename__ = 'Сессия_цитаты'

    id_сессии = Column(String(50), ForeignKey('Сессии.id_сессии', ondelete='CASCADE'), primary_key=True)
    id_цитаты = Column(String(50), ForeignKey('Цитаты.id_цитаты', ondelete='CASCADE'), primary_key=True)
    Время_записи = Column(String(50))
    created_at = Column(TIMESTAMP, server_default='CURRENT_TIMESTAMP')

    сессия = relationship("Сессии", back_populates="сессии_цитаты", overlaps="сессия")
    цитата = relationship("Цитаты", back_populates="сессии_цитаты", overlaps="цитата")