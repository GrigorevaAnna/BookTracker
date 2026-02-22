with open('.env', 'w', encoding='utf-8') as f:
    f.write('DATABASE_URL=postgresql://booktracker_user:5AwI1eCPfQVOHkXKvGbfveaQZYVHoePj@dpg-d5qd7ps9c44c73dkd7m0-a.frankfurt-postgres.render.com/booktracker_q2wq\n')

print("✅ Файл .env создан с правильной кодировкой UTF-8")