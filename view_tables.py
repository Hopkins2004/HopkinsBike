import sqlite3
connection = sqlite3.connect('templates/Thumbs.db')
cursor = connection.cursor()
get_tables = "SELECT name FROM sqlite_master WHERE type='table'"
cursor.execute(get_tables)
tables = cursor.fetchall()
for table in tables:
    print('###################################### This is ',table[0], "#######################################")
    query = "SELECT * from "
    query += table[0]
    cursor.execute(query)
    data = cursor.fetchall()
    for element in data:
        print(element)