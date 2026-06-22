# services/exercise_selector.py

from models.db import db_query_all, db_execute
import random


# ---------------------------------------------------
# Duplicate rules (dynamic during set)
# ---------------------------------------------------

def filter_used_exercises(exercises, used_pairs, used_answers, gs):
    """
    Applies duplicate rules:
    - avoid_duplicate_pairs
    - treat_symmetric_as_duplicates
    - avoid_duplicate_answers

    used_pairs and used_answers come from previous exercises in this set.
    """
    filtered = []

    for ex in exercises:
        a, b, ans = ex["a"], ex["b"], ex["answer"]
        pair = (a, b)
        # avoid duplicate pairs (per operation)
        if gs.get("avoid_duplicate_pairs"):
            if pair in used_pairs:
                continue

        # treat symmetric as duplicate
        if gs.get("treat_symmetric_as_duplicates"):
            if (b, a) in used_pairs:
                continue

        # avoid duplicate answers (global across operations)
        if gs.get("avoid_duplicate_answers"):
            if ans in used_answers:
                continue
        filtered.append(ex)

    return filtered


# ---------------------------------------------------
# Database pool storage
# ---------------------------------------------------
def build_group_pools(group_id, gs):
    """
    Optimized: single INSERT...SELECT per group instead of thousands of INSERTs.
    """

    # remove existing entries
    db_execute(
        "DELETE FROM group_exercise_pools WHERE group_id=:gid",
        {"gid": group_id}
    )

    ops = ['add', 'multiply', 'negation']
    diffs = [1, 2, 3]

    # Build dynamic SQL filters only once
    filters = []
    params = {"gid": group_id, "ops": tuple(ops), "diffs": tuple(diffs)}

    if gs["excluded_a"]:
        a_vals = tuple(map(int, gs["excluded_a"].split(",")))
        filters.append("a NOT IN :excluded_a")
        params["excluded_a"] = a_vals

    if gs["excluded_b"]:
        b_vals = tuple(map(int, gs["excluded_b"].split(",")))
        filters.append("b NOT IN :excluded_b")
        params["excluded_b"] = b_vals

    if gs["excluded_answers"]:
        ans_vals = tuple(map(int, gs["excluded_answers"].split(",")))
        filters.append("answer NOT IN :excluded_answers")
        params["excluded_answers"] = ans_vals

    if gs.get("avoid_tie_problems"):
        filters.append("a <> b")


    where_clause = ""
    if filters:
        where_clause = " AND " + " AND ".join(filters)

    # SINGLE bulk insert SELECT
    sql = f"""
        INSERT INTO group_exercise_pools (group_id, operation, difficulty, exercise_id)
        SELECT :gid, operation, difficulty, id
        FROM exercises_all
        WHERE operation IN :ops
          AND difficulty IN :diffs
          {where_clause}
    """

    db_execute(sql, params)



def load_group_pool(group_id, operation, difficulty):
    rows = db_query_all("""
        SELECT e.id, e.a, e.b, e.answer
        FROM group_exercise_pools g
        JOIN exercises_all e ON e.id = g.exercise_id
        WHERE g.group_id=:gid AND g.operation=:op AND g.difficulty=:d
    """, {"gid": group_id, "op": operation, "d": difficulty})
    return [{"id": r[0], "a": r[1], "b": r[2], "answer": r[3]} for r in rows]



# ---------------------------------------------------
# Full selection logic (per operation)
# ---------------------------------------------------

def select_problem(operation, difficulty, gs, used_pairs, used_answers, group_id):
    exercises = load_group_pool(group_id, operation, difficulty)
    if not exercises:
        return None

    valid = filter_used_exercises(exercises, used_pairs, used_answers, gs)
    if not valid:
        return None

    return random.choice(valid)



# ---------------------------------------------------
# Validation: effective pool size per op + difficulty
# ---------------------------------------------------

def count_effective_exercises(operation, difficulty, gs):
    """
    Returns the number of *actually usable* exercises for a fresh set,
    applying exclusions and duplicate rules.
    """

    # load from DB
    sql = """
        SELECT id, a, b, answer
        FROM exercises_all
        WHERE operation = :op
          AND difficulty = :diff
    """
    params = {"op": operation, "diff": difficulty}
    if gs.get("excluded_a"):
        sql += " AND a NOT IN (" + ",".join(gs["excluded_a"].split(",")) + ")"
    if gs.get("excluded_b"):
        sql += " AND b NOT IN (" + ",".join(gs["excluded_b"].split(",")) + ")"
    if gs.get("excluded_answers"):
        sql += " AND answer NOT IN (" + ",".join(gs["excluded_answers"].split(",")) + ")"

    rows = db_query_all(sql, params)

    exercises = [{"id": r[0], "a": r[1], "b": r[2], "answer": r[3]} for r in rows]

    if not exercises:
        return 0

    used_pairs = set()
    used_answers = set()
    count = 0
    for ex in exercises:
        a, b, ans = ex["a"], ex["b"], ex["answer"]
        pair = (a, b)
        if gs.get("avoid_duplicate_pairs") and pair in used_pairs:
            continue

        if gs.get("treat_symmetric_as_duplicates") and (b, a) in used_pairs:
            continue

        if gs.get("avoid_duplicate_answers") and ans in used_answers:
            continue

        count += 1
        

        used_pairs.add((a, b))
        if gs.get("treat_symmetric_as_duplicates"):
            used_pairs.add((b, a))

        used_answers.add(ans)
    return count


def validate_group_settings(gs):
    """
    Returns error message if invalid, else None.
    Ensures each enabled operation has enough effective exercises
    for each relevant difficulty.
    """

    required = gs["questions_per_set"]
    only_mix = gs["operation_mix_visible"] and not (gs["operation_add_visible"] or gs["operation_multiply_visible"] or gs["operation_negation_visible"])
    ops = ['add', 'multiply', 'negation']
    diffs = [1, 2, 3]
    if only_mix:
        how_many_in_mix = sum([gs["mix_add"], gs["mix_multiply"], gs["mix_negation"]])
    if only_mix:
        required = required // how_many_in_mix
    if gs["difficulty_choice"] == 0 and gs["fixed_difficulty"] == 4:
        required = required // 3

    for op in ops:
        for d in diffs:
            n = count_effective_exercises(op, d, gs)
            
            print(required)
            if n < required:
                return (
                    f"Niet genoeg oefeningen voor operatie '{op}' met moeilijkheid {d}. "
                    f"Gevonden {n}, nodig {required}."
                )

    return None
