# services/points.py

from models.db import db_execute, db_query_one

def get_user_points(student_id):
    row = db_query_one('SELECT points FROM student_points WHERE student_id=:u', {'u': student_id})
    if not row:
        db_execute('INSERT INTO student_points (student_id, points) VALUES (:u, 0)', {'u': student_id})
        return 0
    return row[0]

def add_points(student_id, amount):
    db_execute('INSERT IGNORE INTO student_points (student_id, points) VALUES (:u, 0)', {'u': student_id})
    db_execute('UPDATE student_points SET points = points + :amt WHERE student_id=:u',
               {'amt': amount, 'u': student_id})

