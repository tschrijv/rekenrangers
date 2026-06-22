from dotenv import load_dotenv
load_dotenv()

from extensions import init_engine
from config import Config
from models.db import db_execute, db_query_one, db_query_all
import extensions


# -------------------------
# Helper: categorize difficulty
# -------------------------
def difficulty_add(a, b):
    s = a + b
    modsum = (a % 10) + (b % 10)

    # Difficulty 1
    if s < 10:
        return 1

    # Difficulty 2
    if (a < 10 and b < 10 and s >= 10) or (a >= 10 and b < 10 and modsum < 10) or (a < 10 and b >= 10 and modsum < 10) or (a >= 10 and b >= 10 and modsum < 10):
        return 2

    # Difficulty 3
    if (a >= 10 and b >= 10 and modsum >= 10):
        return 3

    return None


def difficulty_multiply(a, b):
    prod = a * b
    

    # Difficulty 1
    if prod <= 25:
        return 1

    # Difficulty 2: both operands single-digit
    if a <= 10 and b <= 10:
        return 2

    # Difficulty 3: exactly one operand single digit
    if (a <= 20) and (b <= 20) and ((a <= 10) != (b <= 10)):
        return 3

    return None


def difficulty_negation(a, b):
    if a < b:
        return None

    val = a - b
    moddiff = (a % 10) - (b % 10)

    # Difficulty 1
    if (val < 10 and a < 10 and b < 10):
        return 1

    # Difficulty 2
    if (a >= 10 and b < 10 and moddiff >= 0) or (a < 10 and b >= 10 and moddiff >= 0) or (a >= 10 and b >= 10 and moddiff >= 0):
        return 2

    # Difficulty 3
    if (a >= 10 and b >= 10 and moddiff < 0):
        return 3

    return None


# -------------------------
# Generator Functions
# -------------------------

def generate_addition():
    rows = []
    for a in range(0, 99):
        for b in range(0, 99):
            diff = difficulty_add(a, b)
            if diff is None:
                continue
            answer = a + b
            rows.append(("add", a, b, answer, diff))
    return rows


def generate_multiplication():
    rows = []
    for a in range(0, 20):
        for b in range(0, 20):
            diff = difficulty_multiply(a, b)
            if diff is None:
                continue
            answer = a * b
            rows.append(("multiply", a, b, answer, diff))
    return rows


def generate_negation():
    rows = []
    for a in range(0, 99):
        for b in range(0, 99):
            diff = difficulty_negation(a, b)
            if diff is None:
                continue
            answer = a - b
            rows.append(("negation", a, b, answer, diff))
    return rows


# -------------------------
# MAIN
# -------------------------

def main():

    # Init DB engine
    init_engine(Config.DATABASE_URL)

    print("Clearing old exercises...")
    db_execute("DELETE FROM exercises_all")

    all_rows = []

    print("Generating addition...")
    add_rows = generate_addition()
    all_rows.extend(add_rows)

    print("Generating multiplication...")
    mult_rows = generate_multiplication()
    all_rows.extend(mult_rows)

    print("Generating negation...")
    neg_rows = generate_negation()
    all_rows.extend(neg_rows)

    print(f"Total exercises generated: {len(all_rows)}")

    print("Inserting into database...")
    for op, a, b, ans, diff in all_rows:
        db_execute('''
            INSERT INTO exercises_all (operation, a, b, answer, difficulty)
            VALUES (:op, :a, :b, :ans, :diff)
        ''', {
            'op': op,
            'a': a,
            'b': b,
            'ans': ans,
            'diff': diff
        })

    # Summary per operation/difficulty
    print("\nSummary:")
    for op in ["add", "multiply", "negation"]:
        for d in [1, 2, 3]:
            c = db_query_one('''
                SELECT COUNT(*) FROM exercises_all
                WHERE operation=:op AND difficulty=:d
            ''', {'op': op, 'd': d})[0]
            print(f"{op} (diff {d}): {c}")

    print("\nDone!")


if __name__ == "__main__":
    main()
