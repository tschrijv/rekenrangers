from sqlalchemy import text
import extensions
from config import Config



def db_execute(sql, params=None):
    with extensions.engine.begin() as conn:
        conn.execute(text(sql), params or {})

def db_query_all(sql, params=None):
    with extensions.engine.connect() as conn:
        res = conn.execute(text(sql), params or {})
        return res.fetchall()

def db_query_one(sql, params=None):
    with extensions.engine.connect() as conn:
        res = conn.execute(text(sql), params or {})
        return res.fetchone()
    
def add_puzzle(name: str, img: str, rows: int, cols: int, cost: int):
    db_execute('''
        INSERT IGNORE INTO puzzles
        (name, image_path, rows_count, cols_count, piece_cost)
        VALUES (:n, :img, :r, :c, :cost)

    ''', {
        'n': name,
        'img': img,
        'r': rows,
        'c': cols,
        'cost': cost
    })


def init_db():
    # TEACHERS
    db_execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            password VARCHAR(255)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')


    # GROUPS
    db_execute('''
        CREATE TABLE IF NOT EXISTS `groups` (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            teacher_id INT,
            UNIQUE(name, teacher_id),
            activation_code VARCHAR(32) UNIQUE NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
               
            allow_timer_choice TINYINT(1) DEFAULT 1,
            fixed_show_timer TINYINT(1) DEFAULT 1,
            difficulty_choice TINYINT(1) DEFAULT 1,
            fixed_difficulty TINYINT(1) DEFAULT 2,
               
            operation_add_visible TINYINT(1) DEFAULT 1,
            operation_multiply_visible TINYINT(1) DEFAULT 1,
            operation_negation_visible TINYINT(1) DEFAULT 1,
            operation_mix_visible TINYINT(1) DEFAULT 1,

            mix_add TINYINT(1) DEFAULT 1,
            mix_multiply TINYINT(1) DEFAULT 1,
            mix_negation TINYINT(1) DEFAULT 1,
               
            questions_per_set INT DEFAULT 10,
            meta_prompt_mode TINYINT(1) DEFAULT 1,
               
            fixation_screen TINYINT(1) DEFAULT 0,
            demo_metacognition TINYINT(1) DEFAULT 0,
            research_mode TINYINT(1) DEFAULT 0,
               
            avoid_duplicate_pairs TINYINT(1) DEFAULT 0,
            avoid_duplicate_answers TINYINT(1) DEFAULT 0,
            treat_symmetric_as_duplicates TINYINT(1) DEFAULT 0,
            avoid_tie_problems TINYINT(1) DEFAULT 0,
            operand_position_counterbalancing TINYINT(1) DEFAULT 0,

            excluded_a TEXT DEFAULT NULL,
            excluded_b TEXT DEFAULT NULL,
            excluded_answers TEXT DEFAULT NULL,

            FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE SET NULL   
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

    # STUDENTS
    db_execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(255) NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            difficulty_elo INT DEFAULT 450,
            group_id INT,
            current_step INT DEFAULT 1,
            pin VARCHAR(10) DEFAULT '0000',
            demo_seen TINYINT(1) DEFAULT 0,
            UNIQUE(username, group_id),
            FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

    # STUDENT POINTS
    db_execute('''
        CREATE TABLE IF NOT EXISTS student_points (
            student_id INT PRIMARY KEY,
            points INT DEFAULT 0,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')


    # EXERCISES
    db_execute('''
        CREATE TABLE IF NOT EXISTS exercises (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            set_id INT NOT NULL,
            operation VARCHAR(20),
            a INT,
            b INT,
            user_answer INT,
            correct_answer INT,
            is_correct TINYINT(1),
            response_time DOUBLE,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            difficulty TINYINT(1),
            show_timer TINYINT(1),
            meta_self_score TINYINT DEFAULT 0,
            time_self_score DOUBLE,
            time_feedback DOUBLE,
            current_elo INT,
            delta_elo INT,
            current_difficulty_zone INT,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

    # PUZZLES
    db_execute('''
        CREATE TABLE IF NOT EXISTS puzzles (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            image_path VARCHAR(255) UNIQUE NOT NULL,
            rows_count INT DEFAULT 4,
            cols_count INT DEFAULT 5,
            piece_cost INT DEFAULT 10
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

    # USER PUZZLE PIECES
    db_execute('''
        CREATE TABLE IF NOT EXISTS student_puzzle_pieces (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            puzzle_id INT NOT NULL,
            piece_index INT NOT NULL,
            UNIQUE(student_id, puzzle_id, piece_index),
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
            FOREIGN KEY (puzzle_id) REFERENCES puzzles(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

     # MASTER EXERCISE TABLE (ALL POSSIBLE EXERCISES)
    db_execute('''
        CREATE TABLE IF NOT EXISTS exercises_all (
            id INT AUTO_INCREMENT PRIMARY KEY,
            operation ENUM('add', 'multiply', 'negation') NOT NULL,
            a INT NOT NULL,
            b INT NOT NULL,
            answer INT NOT NULL,
            difficulty TINYINT NOT NULL CHECK (difficulty IN (1,2,3)),
            UNIQUE(operation, a, b)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

    db_execute('''
        CREATE TABLE IF NOT EXISTS group_exercise_pools (
            id INT AUTO_INCREMENT PRIMARY KEY,
            group_id INT NOT NULL,
            operation ENUM('add','multiply','negation') NOT NULL,
            difficulty TINYINT NOT NULL,
            exercise_id INT NOT NULL,
            FOREIGN KEY (exercise_id) REFERENCES exercises_all(id) ON DELETE CASCADE,
            INDEX(group_id),
            INDEX(group_id, operation, difficulty)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')

        # EXERCISE SEQUENCES (per group)
    db_execute('''
        CREATE TABLE IF NOT EXISTS exercise_sequences (
            id INT AUTO_INCREMENT PRIMARY KEY,
            group_id INT NOT NULL,
            name VARCHAR(255) NOT NULL DEFAULT 'Standaardreeks',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES `groups`(id) ON DELETE CASCADE,
            UNIQUE (group_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')


        # EXERCISE SEQUENCE STEPS (each step has its own settings)
    db_execute('''
        CREATE TABLE IF NOT EXISTS exercise_sequence_steps (
            id INT AUTO_INCREMENT PRIMARY KEY,
            sequence_id INT NOT NULL,
            position INT NOT NULL,

            questions_per_set INT DEFAULT 10,
            meta_prompt_mode TINYINT(1) DEFAULT 1,

            allow_timer_choice TINYINT(1) DEFAULT 1,
            fixed_show_timer TINYINT(1) DEFAULT 1,
            difficulty_choice TINYINT(1) DEFAULT 1,
            fixed_difficulty TINYINT(1) DEFAULT 2,

            operation_add_visible TINYINT(1) DEFAULT 1,
            operation_multiply_visible TINYINT(1) DEFAULT 1,
            operation_negation_visible TINYINT(1) DEFAULT 1,
            operation_mix_visible TINYINT(1) DEFAULT 1,

            mix_add TINYINT(1) DEFAULT 1,
            mix_multiply TINYINT(1) DEFAULT 1,
            mix_negation TINYINT(1) DEFAULT 1,

            FOREIGN KEY (sequence_id) REFERENCES exercise_sequences(id) ON DELETE CASCADE,
            INDEX(sequence_id),
            INDEX(sequence_id, position)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    
    
    add_puzzle('Giraf', '/static/puzzles/giraf.png', 5, 3, 10)
    add_puzzle('Leeuw', '/static/puzzles/lion.png', 5, 3, 30)
    add_puzzle('Olifant', '/static/puzzles/elephant.png', 5, 3, 15)
    add_puzzle('Neushoorn', '/static/puzzles/rhino.png', 5, 3, 20)
    add_puzzle('Nijlpaard', '/static/puzzles/hippo.png', 5, 3, 25)
    add_puzzle('Zebra', '/static/puzzles/zebra.png', 5, 3, 5)

    







