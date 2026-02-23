import psycopg2
import ssl
import socket

# ВАШ ТОЧНЫЙ URL ИЗ RENDER (скопируйте из панели Connections)
DATABASE_URL = "postgresql://booktracker_user:TgwCFLfy0zHY2vBKEiiAhWpeyqcYpNfI@dpg-d6e6pnbh46gs73e06sk0-a.oregon-postgres.render.com/booktracker_q2wq_sycn"

print("=" * 60)
print("ТЕСТ ПОДКЛЮЧЕНИЯ К RENDER POSTGRESQL")
print("=" * 60)

# 1. Сначала проверим доступность хоста
host = "dpg-d6e6pnbh46gs73e06sk0-a.oregon-postgres.render.com"
port = 5432

print(f"\n1. Проверка доступности {host}:{port}...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex((host, port))
    if result == 0:
        print("✅ Хост доступен, порт открыт")
    else:
        print(f"❌ Хост недоступен, код ошибки: {result}")
    sock.close()
except Exception as e:
    print(f"❌ Ошибка при проверке: {e}")

# 2. Пробуем подключиться с разными настройками SSL
print("\n2. Попытка подключения с sslmode='require'...")
try:
    conn = psycopg2.connect(
        DATABASE_URL,
        sslmode='require',
        connect_timeout=10,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5
    )
    print("✅ ПОДКЛЮЧЕНИЕ УСПЕШНО!")

    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()
    print(f"   Версия PostgreSQL: {version[0]}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"❌ Ошибка: {e}")

    # 3. Пробуем с sslmode='prefer'
    print("\n3. Попытка с sslmode='prefer'...")
    try:
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode='prefer',
            connect_timeout=10
        )
        print("✅ Подключение с 'prefer' успешно!")
        conn.close()
    except Exception as e2:
        print(f"❌ Ошибка с 'prefer': {e2}")

        # 4. Пробуем без SSL (не рекомендуется, но для теста)
        print("\n4. Попытка без SSL (sslmode='disable')...")
        try:
            conn = psycopg2.connect(
                DATABASE_URL,
                sslmode='disable',
                connect_timeout=10
            )
            print("✅ Подключение без SSL успешно!")
            conn.close()
        except Exception as e3:
            print(f"❌ Ошибка без SSL: {e3}")

print("\n" + "=" * 60)