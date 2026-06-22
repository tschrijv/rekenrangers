from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, Response
)
from datetime import datetime
from random import randint
import csv, io, json

from models.db import db_query_one, db_query_all, db_execute
from services.exercise_selector import validate_group_settings, build_group_pools
from services.animals import pin_to_animals
from services.exercise_selector import select_problem

teacher_bp = Blueprint("teacher", __name__, url_prefix="/teacher")


# -----------------------------
# HELPERS
# -----------------------------
def teacher_owns_group(teacher_id, group_id):
    row = db_query_one(
        'SELECT id FROM `groups` WHERE id=:g AND teacher_id=:t',
        {'g': group_id, 't': teacher_id}
    )
    return row is not None

def get_or_create_sequence_for_group(group_id):
    """
    Zorgt dat er precies één exercise_sequence voor deze groep is.
    Retourneert het sequence_id.
    """
    row = db_query_one(
        'SELECT id FROM exercise_sequences WHERE group_id=:g',
        {'g': group_id}
    )
    if row:
        return row[0]

    db_execute('''
        INSERT INTO exercise_sequences (group_id, name, created_at)
        VALUES (:g, :n, NOW())
    ''', {'g': group_id, 'n': 'Standaardreeks'})

    row = db_query_one(
        'SELECT id FROM exercise_sequences WHERE group_id=:g',
        {'g': group_id}
    )
    return row[0]

import random

def build_preview_exercise(group_id, gs):
    visible_ops = []
    if gs['operation_add_visible']:
        visible_ops.append('add')
    if gs['operation_multiply_visible']:
        visible_ops.append('multiply')
    if gs['operation_negation_visible']:
        visible_ops.append('negation')
    if gs['operation_mix_visible']:
        visible_ops.append('mix')

    if not visible_ops:
        return None

    chosen_mode = visible_ops[0]

    if chosen_mode == 'mix':
        mix_ops = []
        if gs['mix_add']:
            mix_ops.append('add')
        if gs['mix_multiply']:
            mix_ops.append('multiply')
        if gs['mix_negation']:
            mix_ops.append('negation')
        if not mix_ops:
            return None
        operation = random.choice(mix_ops)
    else:
        operation = chosen_mode

    if gs['difficulty_choice'] == 0:
        difficulty = gs['fixed_difficulty']
        if difficulty == 4:
            difficulty = random.choice([1, 2, 3])
    else:
        difficulty = random.choice([1, 2, 3])

    if difficulty not in (1, 2, 3):
        difficulty = 2

    ex = select_problem(
        operation=operation,
        difficulty=difficulty,
        gs=gs,
        used_pairs=set(),
        used_answers=set(),
        group_id=group_id
    )

    if ex is None:
        return None

    a = ex["a"]
    b = ex["b"]

    if gs.get("operand_position_counterbalancing") and operation in ("add", "multiply"):
        desired = random.choice(["left", "right"])
        if desired == "left" and a < b:
            a, b = b, a
        elif desired == "right" and a > b:
            a, b = b, a

    return {
        "a": a,
        "b": b,
        "operation": operation,
        "difficulty": difficulty,
        "mode": chosen_mode,
        "show_timer": gs["fixed_show_timer"],
        "meta_prompt_mode": gs["meta_prompt_mode"],
        "fixation_screen": gs["fixation_screen"]
    }


def load_preview_settings_for_group(group_id, step_id=None):
    g_row = db_query_one('''
        SELECT
            questions_per_set, meta_prompt_mode,
            allow_timer_choice, fixed_show_timer,
            difficulty_choice, fixed_difficulty,
            operation_add_visible, operation_multiply_visible,
            operation_negation_visible, operation_mix_visible,
            mix_add, mix_multiply, mix_negation,
            fixation_screen, demo_metacognition, research_mode,
            avoid_duplicate_pairs, avoid_duplicate_answers,
            treat_symmetric_as_duplicates, avoid_tie_problems,
            operand_position_counterbalancing,
            excluded_a, excluded_b, excluded_answers
        FROM `groups`
        WHERE id=:gid
    ''', {'gid': group_id})

    gs = {
        'questions_per_set': g_row[0] or 10,
        'meta_prompt_mode': g_row[1] if g_row[1] is not None else 1,
        'allow_timer_choice': bool(g_row[2]),
        'fixed_show_timer': bool(g_row[3]),
        'difficulty_choice': int(g_row[4]),
        'fixed_difficulty': g_row[5] or 2,
        'operation_add_visible': bool(g_row[6]),
        'operation_multiply_visible': bool(g_row[7]),
        'operation_negation_visible': bool(g_row[8]),
        'operation_mix_visible': bool(g_row[9]),
        'mix_add': bool(g_row[10]),
        'mix_multiply': bool(g_row[11]),
        'mix_negation': bool(g_row[12]),
        'fixation_screen': bool(g_row[13]),
        'demo_metacognition': bool(g_row[14]),
        'research_mode': bool(g_row[15]),
        'avoid_duplicate_pairs': bool(g_row[16]),
        'avoid_duplicate_answers': bool(g_row[17]),
        'treat_symmetric_as_duplicates': bool(g_row[18]),
        'avoid_tie_problems': bool(g_row[19]),
        'operand_position_counterbalancing': bool(g_row[20]),
        'excluded_a': g_row[21] or '',
        'excluded_b': g_row[22] or '',
        'excluded_answers': g_row[23] or '',
    }

    if step_id is not None:
        step_row = db_query_one('''
            SELECT
                s.questions_per_set, s.meta_prompt_mode,
                s.allow_timer_choice, s.fixed_show_timer,
                s.difficulty_choice, s.fixed_difficulty,
                s.operation_add_visible, s.operation_multiply_visible,
                s.operation_negation_visible, s.operation_mix_visible,
                s.mix_add, s.mix_multiply, s.mix_negation
            FROM exercise_sequence_steps s
            JOIN exercise_sequences seq ON seq.id = s.sequence_id
            WHERE s.id=:sid AND seq.group_id=:gid
        ''', {'sid': step_id, 'gid': group_id})

        if step_row:
            gs.update({
                'questions_per_set': step_row[0] or 10,
                'meta_prompt_mode': step_row[1] if step_row[1] is not None else 1,
                'allow_timer_choice': bool(step_row[2]),
                'fixed_show_timer': bool(step_row[3]),
                'difficulty_choice': int(step_row[4]),
                'fixed_difficulty': step_row[5] or 2,
                'operation_add_visible': bool(step_row[6]),
                'operation_multiply_visible': bool(step_row[7]),
                'operation_negation_visible': bool(step_row[8]),
                'operation_mix_visible': bool(step_row[9]),
                'mix_add': bool(step_row[10]),
                'mix_multiply': bool(step_row[11]),
                'mix_negation': bool(step_row[12]),
            })

    return gs


def get_group_research_settings(group_id):
    row = db_query_one('''
        SELECT
            fixation_screen,
            demo_metacognition,
            research_mode,
            avoid_duplicate_pairs,
            avoid_duplicate_answers,
            treat_symmetric_as_duplicates,
            avoid_tie_problems,
            operand_position_counterbalancing,
            excluded_a,
            excluded_b,
            excluded_answers
        FROM `groups`
        WHERE id=:gid
    ''', {'gid': group_id})

    if not row:
        return None

    return {
        'fixation_screen': row[0],
        'demo_metacognition': row[1],
        'research_mode': row[2],
        'avoid_duplicate_pairs': row[3],
        'avoid_duplicate_answers': row[4],
        'treat_symmetric_as_duplicates': row[5],
        'avoid_tie_problems': row[6],
        'operand_position_counterbalancing': row[7],
        'excluded_a': row[8] or '',
        'excluded_b': row[9] or '',
        'excluded_answers': row[10] or ''
    }


def build_validation_settings(step_settings, research_settings):
    """
    Combineer stap/groepsinstellingen met onderzoeksinstellingen
    tot het formaat dat validate_group_settings verwacht.
    """
    return {
        'questions_per_set': step_settings['questions_per_set'],
        'operation_add_visible': step_settings['operation_add_visible'],
        'operation_multiply_visible': step_settings['operation_multiply_visible'],
        'operation_negation_visible': step_settings['operation_negation_visible'],
        'operation_mix_visible': step_settings['operation_mix_visible'],
        'mix_add': step_settings['mix_add'],
        'mix_multiply': step_settings['mix_multiply'],
        'mix_negation': step_settings['mix_negation'],
        'difficulty_choice': step_settings['difficulty_choice'],
        'fixed_difficulty': step_settings['fixed_difficulty'],
        'excluded_a': research_settings['excluded_a'],
        'excluded_b': research_settings['excluded_b'],
        'excluded_answers': research_settings['excluded_answers'],
        'avoid_duplicate_pairs': research_settings['avoid_duplicate_pairs'],
        'avoid_duplicate_answers': research_settings['avoid_duplicate_answers'],
        'treat_symmetric_as_duplicates': research_settings['treat_symmetric_as_duplicates'],
        'avoid_tie_problems': research_settings['avoid_tie_problems']
    }


def has_active_sequence(group_id):
    row = db_query_one('''
        SELECT COUNT(*)
        FROM exercise_sequence_steps s
        JOIN exercise_sequences seq ON seq.id = s.sequence_id
        WHERE seq.group_id=:gid
    ''', {'gid': group_id})

    return bool(row and row[0] > 0)



# -----------------------------
# DASHBOARD
# -----------------------------
@teacher_bp.route("/dashboard")
def dashboard():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    groups = db_query_all(
        'SELECT id, name, activation_code, created_at '
        'FROM `groups` WHERE teacher_id=:t ORDER BY id DESC',
        {'t': teacher_id}
    )

    return render_template('teacher_dashboard.html', groups=groups, scroll_page=True)


# -----------------------------
# DELETE GROUP
# -----------------------------
@teacher_bp.route("/delete_group/<int:group_id>", methods=['POST'])
def delete_group(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Je hebt geen toegang tot deze groep!", "danger")
        return redirect(url_for('teacher.dashboard'))

    students = db_query_all(
        'SELECT id FROM students WHERE group_id=:gid',
        {'gid': group_id}
    )

    for (student_id,) in students:
        db_execute('DELETE FROM exercises WHERE student_id=:s', {'s': student_id})
        db_execute('DELETE FROM student_points WHERE student_id=:s', {'s': student_id})
        db_execute('DELETE FROM student_puzzle_pieces WHERE student_id=:s', {'s': student_id})
        db_execute('DELETE FROM students WHERE id=:s', {'s': student_id})

    db_execute('DELETE FROM `groups` WHERE id=:gid', {'gid': group_id})

    flash("Groep en bijhorende leerlingen zijn verwijderd.", "success")
    return redirect(url_for('teacher.dashboard'))

@teacher_bp.route("/import_students", methods=["POST"])
def import_students():
    if "username" not in session or session.get("role") != "teacher":
        return redirect(url_for("auth.login_teacher"))

    teacher_id = db_query_one(
        "SELECT id FROM teachers WHERE username=:u",
        {"u": session["username"]}
    )[0]

    file = request.files.get("file")
    if not file:
        flash("Geen bestand gekozen!", "danger")
        return redirect(url_for("teacher.dashboard"))

    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.reader(stream)
        rows = list(reader)
    except Exception as e:
        print("Error reading CSV:", e)
        flash("Kon bestand niet lezen! Zorg voor een CSV bestand.", "danger")
        return redirect(url_for("teacher.dashboard"))

    if len(rows) < 2:
        flash("Bestand bevat geen gegevens!", "danger")
        return redirect(url_for("teacher.dashboard"))

    # Skip header
    rows = rows[1:]

    group_ids = {}

    for row in rows:
        if len(row) < 3:
            continue

        first, last, group_name = map(str.strip, row[:3])
        full_name = f"{first} {last}".strip()
        pin = str(randint(1000, 9999))

        if not first or not last or not group_name:
            continue

        # Get/create group for this teacher
        if group_name not in group_ids:
            try:
                db_execute("""
                    INSERT INTO `groups` (name, teacher_id, activation_code, created_at)
                    VALUES (:g, :t, SUBSTRING(MD5(RAND()), 1, 6), NOW())
                """, {"g": group_name, "t": teacher_id})
            except Exception:
                pass  # group may already exist

            gid = db_query_one("""
                SELECT id FROM `groups`
                WHERE name=:g AND teacher_id=:t
            """, {"g": group_name, "t": teacher_id})[0]

            group_ids[group_name] = gid

        gid = group_ids[group_name]

        # Insert student
        try:
            db_execute("""
                INSERT INTO students (username, created_at, group_id, pin)
                VALUES (:u, NOW(), :gid, :p)
            """, {"u": full_name, "gid": gid, "p": pin})
        except Exception:
            pass  # likely already exists — skip gracefully

    flash("Leerlingen succesvol geïmporteerd!", "success")
    return redirect(url_for("teacher.dashboard"))


# -----------------------------
# GROUP DETAIL + ADD STUDENT + SETTINGS PAGE
# -----------------------------
@teacher_bp.route("/group/<int:group_id>", methods=['GET', 'POST'])
def group(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Je hebt geen toegang tot deze groep!", "danger")
        return redirect(url_for('teacher.dashboard'))

    # -------------------------
    # ADD STUDENT
    # -------------------------
    if request.method == 'POST':
        name = (request.form.get('student_name') or '').strip()
        pin = str(randint(1000, 9999))
        if not name:
            flash("Naam mag niet leeg zijn.", "warning")
            return redirect(url_for('teacher.group', group_id=group_id))

        try:
            db_execute('''
                INSERT INTO students (username, created_at, group_id, pin)
                VALUES (:u, :t, :g, :p)
            ''', {
                'u': name,
                't': datetime.now().isoformat(),
                'g': group_id,
                'p': pin
            })
            flash("Leerling toegevoegd!", "success")
        except Exception:
            flash("Leerling toevoegen mislukt! De leerling bestaat al.", "danger")

        return redirect(url_for('teacher.group', group_id=group_id))

    # -------------------------
    # LOAD GROUP + SETTINGS
    # -------------------------
    g_row = db_query_one('''
        SELECT
            name, activation_code,
            allow_timer_choice, fixed_show_timer,
            difficulty_choice, fixed_difficulty,

            operation_add_visible, operation_multiply_visible,
            operation_negation_visible, operation_mix_visible,

            mix_add, mix_multiply, mix_negation,

            questions_per_set, meta_prompt_mode,
                         
            fixation_screen, demo_metacognition, research_mode,

            avoid_duplicate_pairs, avoid_duplicate_answers,
            treat_symmetric_as_duplicates, avoid_tie_problems, operand_position_counterbalancing,

            excluded_a, excluded_b, excluded_answers
        FROM `groups`
        WHERE id=:gid
    ''', {'gid': group_id})

    if not g_row:
        return "Groep niet gevonden."

    group_info = (g_row[0], g_row[1])  # name, activation_code

    settings = {
        'allow_timer_choice': bool(g_row[2]),
        'fixed_show_timer': bool(g_row[3]),
        'difficulty_choice': g_row[4],
        'fixed_difficulty': g_row[5],
        'operation_add_visible': bool(g_row[6]),
        'operation_multiply_visible': bool(g_row[7]),
        'operation_negation_visible': bool(g_row[8]),
        'operation_mix_visible': bool(g_row[9]),
        'mix_add': bool(g_row[10]),
        'mix_multiply': bool(g_row[11]),
        'mix_negation': bool(g_row[12]),
        'questions_per_set': g_row[13] or 10,
        'meta_prompt_mode': g_row[14] if g_row[14] is not None else 1,
        'fixation_screen': bool(g_row[15]),
        'demo_metacognition': bool(g_row[16]),
        'research_mode': bool(g_row[17]),
        'avoid_duplicate_pairs': bool(g_row[18]),
        'avoid_duplicate_answers': bool(g_row[19]),
        'treat_symmetric_as_duplicates': bool(g_row[20]),
        'avoid_tie_problems': bool(g_row[21]),
        'operand_position_counterbalancing': bool(g_row[22]),
        'excluded_a': g_row[23] or '',
        'excluded_b': g_row[24] or '',
        'excluded_answers': g_row[25] or ''
    }

    students = db_query_all(
    '''
    SELECT id, username, current_step, pin, difficulty_elo
    FROM students
    WHERE group_id = :gid
    ORDER BY username
    ''',
    {'gid': group_id}
    )


    # Pin emojis toevoegen
    students = [(s[0], s[1], s[2], s[3], pin_to_animals(s[3]), s[4]) for s in students]

    
    # Load sequence info for group
    seq_row = db_query_one(
        'SELECT id FROM exercise_sequences WHERE group_id=:g',
        {'g': group_id}
    )

    if seq_row:
        sequence_id = seq_row[0]
        step_count_row = db_query_one(
            'SELECT COUNT(*) FROM exercise_sequence_steps WHERE sequence_id=:sid',
            {'sid': sequence_id}
        )
        total_steps = step_count_row[0] if step_count_row else 0
    else:
        total_steps = 0


    return render_template(
        'teacher_group.html',
        group_id=group_id,
        group=group_info,
        students=students,
        group_settings=settings,
        scroll_page=True,
        total_steps=total_steps,
        mouse_locked=False,
        **settings  # pass settings explicitly to template variables
    )


# -----------------------------
# UPDATE GROUP SETTINGS
# -----------------------------
@teacher_bp.route("/group/<int:group_id>/settings", methods=['POST'])
def update_group_settings(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    f = request.form

    allow_timer_choice = 1 if 'allow_timer_choice' in f else 0
    fixed_show_timer = int(f.get('fixed_show_timer', 1))
    difficulty_choice = int(f.get('difficulty_choice', 0))
    fixed_difficulty = int(f.get('fixed_difficulty', 2))
    questions_per_set = int(f.get('questions_per_set', 10))
    meta_prompt_mode = int(f.get('meta_prompt_mode', 1))

    operation_add_visible = 1 if 'operation_add_visible' in f else 0
    operation_multiply_visible = 1 if 'operation_multiply_visible' in f else 0
    operation_negation_visible = 1 if 'operation_negation_visible' in f else 0
    operation_mix_visible = 1 if 'operation_mix_visible' in f else 0

    mix_add = 1 if 'mix_add' in f else 0
    mix_multiply = 1 if 'mix_multiply' in f else 0
    mix_negation = 1 if 'mix_negation' in f else 0

    fixation_screen = 1 if 'fixation_screen' in f else 0
    demo_metacognition = 1 if 'demo_metacognition' in f else 0
    research_mode = 1 if 'research_mode' in f else 0

    avoid_duplicate_pairs = 1 if 'avoid_duplicate_pairs' in f else 0
    avoid_duplicate_answers = 1 if 'avoid_duplicate_answers' in f else 0
    treat_symmetric_as_duplicates = 1 if 'treat_symmetric_as_duplicates' in f else 0
    avoid_tie_problems = 1 if 'avoid_tie_problems' in f else 0
    operand_position_counterbalancing = 1 if 'operand_position_counterbalancing' in f else 0

    excluded_a = (f.get('excluded_a') or '').strip()
    excluded_b = (f.get('excluded_b') or '').strip()
    excluded_answers = (f.get('excluded_answers') or '').strip()

    

    # onderzoeksinstellingen zoals nieuw ingevuld op het groepsscherm
    new_research_settings = {
        'fixation_screen': fixation_screen,
        'demo_metacognition': demo_metacognition,
        'research_mode': research_mode,
        'avoid_duplicate_pairs': avoid_duplicate_pairs,
        'avoid_duplicate_answers': avoid_duplicate_answers,
        'treat_symmetric_as_duplicates': treat_symmetric_as_duplicates,
        'avoid_tie_problems': avoid_tie_problems,
        'operand_position_counterbalancing': operand_position_counterbalancing,
        'excluded_a': excluded_a,
        'excluded_b': excluded_b,
        'excluded_answers': excluded_answers
    }

    # standaard groepsinstellingen (nodig als er geen reeks actief is)
    group_step_settings = {
        'questions_per_set': questions_per_set,
        'operation_add_visible': operation_add_visible,
        'operation_multiply_visible': operation_multiply_visible,
        'operation_negation_visible': operation_negation_visible,
        'operation_mix_visible': operation_mix_visible,
        'mix_add': mix_add,
        'mix_multiply': mix_multiply,
        'mix_negation': mix_negation,
        'difficulty_choice': difficulty_choice,
        'fixed_difficulty': fixed_difficulty
    }

    # 1) validatie
    if not has_active_sequence(group_id):

        if operation_add_visible + operation_multiply_visible + operation_negation_visible + operation_mix_visible == 0:
            flash("Instellingen opslaan mislukt! Er moet minstens 1 operatie beschikbaar zijn.", "danger")
            return redirect(url_for('teacher.group', group_id=group_id))

        if mix_add + mix_multiply + mix_negation == 0 and operation_mix_visible:
            flash("Instellingen opslaan mislukt! Mix moet minstens 1 operatie bevatten.", "danger")
            return redirect(url_for('teacher.group', group_id=group_id))
        
        validation_settings = build_validation_settings(group_step_settings, new_research_settings)
        error_msg = validate_group_settings(validation_settings)
        if error_msg:
            flash(f"Instellingen opslaan mislukt! {error_msg}", "danger")
            return redirect(url_for('teacher.group', group_id=group_id))
    else:
        steps = db_query_all('''
            SELECT
                s.id,
                s.position,
                s.questions_per_set,
                s.difficulty_choice,
                s.fixed_difficulty,
                s.operation_add_visible,
                s.operation_multiply_visible,
                s.operation_negation_visible,
                s.operation_mix_visible,
                s.mix_add,
                s.mix_multiply,
                s.mix_negation
            FROM exercise_sequence_steps s
            JOIN exercise_sequences seq ON seq.id = s.sequence_id
            WHERE seq.group_id=:gid
            ORDER BY s.position
        ''', {'gid': group_id})

        for step in steps:
            step_settings = {
                'questions_per_set': step[2],
                'difficulty_choice': step[3],
                'fixed_difficulty': step[4],
                'operation_add_visible': step[5],
                'operation_multiply_visible': step[6],
                'operation_negation_visible': step[7],
                'operation_mix_visible': step[8],
                'mix_add': step[9],
                'mix_multiply': step[10],
                'mix_negation': step[11]
            }

            validation_settings = build_validation_settings(step_settings, new_research_settings)
            error_msg = validate_group_settings(validation_settings)
            if error_msg:
                flash(
                    f"Instellingen opslaan mislukt! De nieuwe onderzoeksinstellingen zijn niet compatibel met stap {step[1]} van de oefenreeksreeks. {error_msg}",
                    "danger"
                )
                return redirect(url_for('teacher.group', group_id=group_id))

    # 2) save settings to DB
    db_execute('''
        UPDATE `groups`
        SET allow_timer_choice=:at,
            fixed_show_timer=:fst,
            difficulty_choice=:dc,
            fixed_difficulty=:fd,
            operation_add_visible=:oav,
            operation_multiply_visible=:omv,
            operation_negation_visible=:onv,
            operation_mix_visible=:oxv,
            mix_add=:ma,
            mix_multiply=:mm,
            mix_negation=:mn,
            questions_per_set=:qps,
            meta_prompt_mode=:mpm,
            fixation_screen=:fix,
            demo_metacognition=:demo,
            research_mode=:rm,
            avoid_duplicate_pairs=:adp,
            avoid_duplicate_answers=:ada,
            treat_symmetric_as_duplicates=:tsd,
            avoid_tie_problems=:atp,
            operand_position_counterbalancing=:opc,
            excluded_a=:ea,
            excluded_b=:eb,
            excluded_answers=:eans
        WHERE id=:gid
    ''', {
        'at': allow_timer_choice,
        'fst': fixed_show_timer,
        'dc': difficulty_choice,
        'fd': fixed_difficulty,
        'oav': operation_add_visible,
        'omv': operation_multiply_visible,
        'onv': operation_negation_visible,
        'oxv': operation_mix_visible,
        'ma': mix_add,
        'mm': mix_multiply,
        'mn': mix_negation,
        'qps': questions_per_set,
        'mpm': meta_prompt_mode,
        'fix': fixation_screen,
        'demo': demo_metacognition,
        'rm': research_mode,
        'adp': avoid_duplicate_pairs,
        'ada': avoid_duplicate_answers,
        'tsd': treat_symmetric_as_duplicates,
        'atp': avoid_tie_problems,
        'opc': operand_position_counterbalancing,
        'ea': excluded_a,
        'eb': excluded_b,
        'eans': excluded_answers,
        'gid': group_id
    })

    # 3) heavy step: build all pools (can take up to a minute)
    build_group_pools(group_id, build_validation_settings(group_step_settings, new_research_settings))

    flash("Instellingen opgeslagen en oefenreeksen voorbereid.", "success")
    return redirect(url_for('teacher.group', group_id=group_id))


@teacher_bp.route("/group/<int:group_id>/sequence")
def group_sequence(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Je hebt geen toegang tot deze groep!", "danger")
        return redirect(url_for('teacher.dashboard'))

    sequence_id = get_or_create_sequence_for_group(group_id)

    steps = db_query_all('''
        SELECT id, position,
               questions_per_set, meta_prompt_mode,
               allow_timer_choice, fixed_show_timer,
               difficulty_choice, fixed_difficulty,
               operation_add_visible, operation_multiply_visible,
               operation_negation_visible, operation_mix_visible,
               mix_add, mix_multiply, mix_negation
        FROM exercise_sequence_steps
        WHERE sequence_id=:sid
        ORDER BY position
    ''', {'sid': sequence_id})

    g_row = db_query_one('SELECT name FROM `groups` WHERE id=:gid', {'gid': group_id})
    group_name = g_row[0] if g_row else "Onbekende groep"

    return render_template(
        'teacher_sequence.html',
        group_id=group_id,
        group_name=group_name,
        sequence_id=sequence_id,
        steps=steps,
        scroll_page=True
    )



@teacher_bp.route("/group/<int:group_id>/sequence/add_step", methods=['POST'])
def add_sequence_step(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    sequence_id = get_or_create_sequence_for_group(group_id)
    f = request.form

    # volgende positie
    row = db_query_one(
        'SELECT COALESCE(MAX(position), 0) FROM exercise_sequence_steps WHERE sequence_id=:sid',
        {'sid': sequence_id}
    )
    next_pos = (row[0] if row else 0) + 1

    questions_per_set = int(f.get('questions_per_set', 10))
    meta_prompt_mode = int(f.get('meta_prompt_mode', 1))

    allow_timer_choice = 1 if 'allow_timer_choice' in f else 0
    fixed_show_timer = int(f.get('fixed_show_timer', 1))

    difficulty_choice = int(f.get('difficulty_choice', 0))
    fixed_difficulty = int(f.get('fixed_difficulty', 2))

    operation_add_visible = 1 if 'operation_add_visible' in f else 0
    operation_multiply_visible = 1 if 'operation_multiply_visible' in f else 0
    operation_negation_visible = 1 if 'operation_negation_visible' in f else 0
    operation_mix_visible = 1 if 'operation_mix_visible' in f else 0

    mix_add = 1 if 'mix_add' in f else 0
    mix_multiply = 1 if 'mix_multiply' in f else 0
    mix_negation = 1 if 'mix_negation' in f else 0

    if operation_add_visible + operation_multiply_visible + operation_negation_visible + operation_mix_visible == 0:
        flash("Instellingen opslaan mislukt! Er moet minstens 1 operatie beschikbaar zijn.", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    if mix_add + mix_multiply + mix_negation == 0 and operation_mix_visible:
        flash("Instellingen opslaan mislukt! Mix moet minstens 1 operatie bevatten.", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    research_settings = get_group_research_settings(group_id)
    if not research_settings:
        flash("Onderzoeksinstellingen van de groep konden niet geladen worden.", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    step_settings = {
        'questions_per_set': questions_per_set,
        'difficulty_choice': difficulty_choice,
        'fixed_difficulty': fixed_difficulty,
        'operation_add_visible': operation_add_visible,
        'operation_multiply_visible': operation_multiply_visible,
        'operation_negation_visible': operation_negation_visible,
        'operation_mix_visible': operation_mix_visible,
        'mix_add': mix_add,
        'mix_multiply': mix_multiply,
        'mix_negation': mix_negation
    }

    validation_settings = build_validation_settings(step_settings, research_settings)
    error_msg = validate_group_settings(validation_settings)
    if error_msg:
        flash(f"Stap toevoegen mislukt! {error_msg}", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    db_execute('''
        INSERT INTO exercise_sequence_steps (
            sequence_id, position,
            questions_per_set, meta_prompt_mode,
            allow_timer_choice, fixed_show_timer,
            difficulty_choice, fixed_difficulty,
            operation_add_visible, operation_multiply_visible,
            operation_negation_visible, operation_mix_visible,
            mix_add, mix_multiply, mix_negation
        ) VALUES (
            :sid, :pos,
            :qps, :mpm,
            :at, :fst,
            :dc, :fd,
            :oav, :omv, :onv, :oxv,
            :ma, :mm, :mn
        )
    ''', {
        'sid': sequence_id,
        'pos': next_pos,
        'qps': questions_per_set,
        'mpm': meta_prompt_mode,
        'at': allow_timer_choice,
        'fst': fixed_show_timer,
        'dc': difficulty_choice,
        'fd': fixed_difficulty,
        'oav': operation_add_visible,
        'omv': operation_multiply_visible,
        'onv': operation_negation_visible,
        'oxv': operation_mix_visible,
        'ma': mix_add,
        'mm': mix_multiply,
        'mn': mix_negation
    })

    flash("Stap toegevoegd aan reeks.", "success")
    return redirect(url_for('teacher.group_sequence', group_id=group_id))



@teacher_bp.route("/group/<int:group_id>/sequence/step/<int:step_id>/delete", methods=['POST'])
def delete_sequence_step(group_id, step_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    # delete step
    db_execute('DELETE FROM exercise_sequence_steps WHERE id=:sid', {'sid': step_id})

    # re-pack positions (1,2,3,...)
    sequence_id = get_or_create_sequence_for_group(group_id)
    rows = db_query_all(
        'SELECT id FROM exercise_sequence_steps WHERE sequence_id=:sid ORDER BY position',
        {'sid': sequence_id}
    )
    pos = 1
    for (sid,) in rows:
        db_execute('UPDATE exercise_sequence_steps SET position=:p WHERE id=:id',
                   {'p': pos, 'id': sid})
        pos += 1
    if rows == []:
        flash("Alle stappen in de reeks zijn verwijderd. De groep gebruikt nu weer de standaardinstellingen.", "success")
    else:
        flash("Stap verwijderd.", "success")
    
    return redirect(url_for('teacher.group_sequence', group_id=group_id))


@teacher_bp.route("/group/<int:group_id>/sequence/step/<int:step_id>/edit", methods=["GET"])
def edit_sequence_step(group_id, step_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    # ensure step belongs to this group’s sequence
    row = db_query_one('''
        SELECT s.id, s.position,
               s.questions_per_set, s.meta_prompt_mode,
               s.allow_timer_choice, s.fixed_show_timer,
               s.difficulty_choice, s.fixed_difficulty,
               s.operation_add_visible, s.operation_multiply_visible,
               s.operation_negation_visible, s.operation_mix_visible,
               s.mix_add, s.mix_multiply, s.mix_negation
        FROM exercise_sequence_steps s
        JOIN exercise_sequences seq ON seq.id = s.sequence_id
        WHERE s.id=:sid AND seq.group_id=:gid
    ''', {'sid': step_id, 'gid': group_id})

    if not row:
        flash("Stap niet gevonden.", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    g_row = db_query_one('SELECT name FROM `groups` WHERE id=:gid', {'gid': group_id})
    group_name = g_row[0] if g_row else "Onbekende groep"

    return render_template(
        "teacher_sequence_edit_step.html",
        group_id=group_id,
        group_name=group_name,
        step=row,
        scroll_page=True
    )


@teacher_bp.route("/group/<int:group_id>/sequence/step/<int:step_id>/edit", methods=["POST"])
def update_sequence_step(group_id, step_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    ok = db_query_one('''
        SELECT s.id
        FROM exercise_sequence_steps s
        JOIN exercise_sequences seq ON seq.id = s.sequence_id
        WHERE s.id=:sid AND seq.group_id=:gid
    ''', {'sid': step_id, 'gid': group_id})

    if not ok:
        flash("Stap niet gevonden.", "danger")
        return redirect(url_for('teacher.group_sequence', group_id=group_id))

    f = request.form

    questions_per_set = int(f.get('questions_per_set', 10))
    meta_prompt_mode = int(f.get('meta_prompt_mode', 1))

    allow_timer_choice = 1 if 'allow_timer_choice' in f else 0
    fixed_show_timer = int(f.get('fixed_show_timer', 1))

    difficulty_choice = int(f.get('difficulty_choice', 0))
    fixed_difficulty = int(f.get('fixed_difficulty', 2))

    operation_add_visible = 1 if 'operation_add_visible' in f else 0
    operation_multiply_visible = 1 if 'operation_multiply_visible' in f else 0
    operation_negation_visible = 1 if 'operation_negation_visible' in f else 0
    operation_mix_visible = 1 if 'operation_mix_visible' in f else 0

    mix_add = 1 if 'mix_add' in f else 0
    mix_multiply = 1 if 'mix_multiply' in f else 0
    mix_negation = 1 if 'mix_negation' in f else 0

    if operation_add_visible + operation_multiply_visible + operation_negation_visible + operation_mix_visible == 0:
        flash("Opslaan mislukt! Er moet minstens 1 operatie beschikbaar zijn.", "danger")
        return redirect(url_for('teacher.edit_sequence_step', group_id=group_id, step_id=step_id))

    if mix_add + mix_multiply + mix_negation == 0 and operation_mix_visible:
        flash("Opslaan mislukt! Mix moet minstens 1 operatie bevatten.", "danger")
        return redirect(url_for('teacher.edit_sequence_step', group_id=group_id, step_id=step_id))

    research_settings = get_group_research_settings(group_id)
    if not research_settings:
        flash("Onderzoeksinstellingen van de groep konden niet geladen worden.", "danger")
        return redirect(url_for('teacher.edit_sequence_step', group_id=group_id, step_id=step_id))

    step_settings = {
        'questions_per_set': questions_per_set,
        'difficulty_choice': difficulty_choice,
        'fixed_difficulty': fixed_difficulty,
        'operation_add_visible': operation_add_visible,
        'operation_multiply_visible': operation_multiply_visible,
        'operation_negation_visible': operation_negation_visible,
        'operation_mix_visible': operation_mix_visible,
        'mix_add': mix_add,
        'mix_multiply': mix_multiply,
        'mix_negation': mix_negation
    }

    validation_settings = build_validation_settings(step_settings, research_settings)
    error_msg = validate_group_settings(validation_settings)
    if error_msg:
        flash(f"Opslaan mislukt! {error_msg}", "danger")
        return redirect(url_for('teacher.edit_sequence_step', group_id=group_id, step_id=step_id))

    db_execute('''
        UPDATE exercise_sequence_steps
        SET questions_per_set=:qps,
            meta_prompt_mode=:mpm,
            allow_timer_choice=:at,
            fixed_show_timer=:fst,
            difficulty_choice=:dc,
            fixed_difficulty=:fd,
            operation_add_visible=:oav,
            operation_multiply_visible=:omv,
            operation_negation_visible=:onv,
            operation_mix_visible=:oxv,
            mix_add=:ma,
            mix_multiply=:mm,
            mix_negation=:mn
        WHERE id=:sid
    ''', {
        'qps': questions_per_set,
        'mpm': meta_prompt_mode,
        'at': allow_timer_choice,
        'fst': fixed_show_timer,
        'dc': difficulty_choice,
        'fd': fixed_difficulty,
        'oav': operation_add_visible,
        'omv': operation_multiply_visible,
        'onv': operation_negation_visible,
        'oxv': operation_mix_visible,
        'ma': mix_add,
        'mm': mix_multiply,
        'mn': mix_negation,
        'sid': step_id
    })

    flash("Stap aangepast.", "success")
    return redirect(url_for('teacher.group_sequence', group_id=group_id))



@teacher_bp.route("/group/<int:group_id>/sequence/clear", methods=["POST"])
def clear_sequence_steps(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        "SELECT id FROM teachers WHERE username=:u",
        {"u": session["username"]}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for("teacher.dashboard"))

    sequence_id = get_or_create_sequence_for_group(group_id)

    # Delete all steps
    db_execute("""
        DELETE FROM exercise_sequence_steps
        WHERE sequence_id = :sid
    """, {"sid": sequence_id})

    # Important: also reset students to step 1  
    # Otherwise leftover values from old sequences cause issues.
    db_execute("""
        UPDATE students
        SET current_step = 1
        WHERE group_id = :gid
    """, {"gid": group_id})

    flash("Alle stappen in de reeks zijn verwijderd. De groep gebruikt nu weer de standaardinstellingen.", "success")
    return redirect(url_for("teacher.group_sequence", group_id=group_id))


@teacher_bp.route("/group/<int:group_id>/sequence/reset_students", methods=["POST"])
def reset_sequence_students(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        "SELECT id FROM teachers WHERE username=:u",
        {"u": session["username"]}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for("teacher.dashboard"))

    # Reset every student in group to step 1
    db_execute("""
        UPDATE students
        SET current_step = 1
        WHERE group_id = :gid
    """, {"gid": group_id})

    flash("Alle leerlingen opnieuw gestart vanaf stap 1.", "success")
    return redirect(url_for("teacher.group_sequence", group_id=group_id))




# -----------------------------
# CREATE GROUP
# -----------------------------
@teacher_bp.route("/create_group", methods=['POST'])
def create_group():
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    name = request.form['group_name'].strip()
    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    import secrets
    activation = secrets.token_hex(3).upper()

    try:
        db_execute('''
            INSERT INTO `groups` (name, teacher_id, activation_code, created_at)
            VALUES (:n, :t, :a, NOW())
        ''', {'n': name, 't': teacher_id, 'a': activation})
        flash("Groep aangemaakt!", "success")
    except Exception:
        flash("Groepsnaam bestaat al!", "danger")

    return redirect(url_for('teacher.dashboard'))


# -----------------------------
# TEACHER VIEW STUDENT
# -----------------------------
@teacher_bp.route("/student/<int:student_id>")
def student(student_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    row = db_query_one('''
        SELECT s.username, s.group_id
        FROM students s
        JOIN `groups` g ON g.id = s.group_id
        WHERE s.id=:u AND g.teacher_id=:t
    ''', {'u': student_id, 't': teacher_id})

    if not row:
        flash("Leerling niet gevonden.", "danger")
        return redirect(url_for('teacher.dashboard'))

    username, group_id = row

    group_name = None
    if group_id:
        g = db_query_one('SELECT name FROM `groups` WHERE id=:gid', {'gid': group_id})
        group_name = g[0] if g else None

    exercises = db_query_all('''
        SELECT set_id, operation, a, b, user_answer, correct_answer,
               is_correct, response_time, difficulty, show_timer, meta_self_score
        FROM exercises
        WHERE student_id=:uid
        ORDER BY set_id, id
    ''', {'uid': student_id})

    return render_template(
        'teacher_student.html',
        username=username,
        group_name=group_name,
        exercises=exercises,
        group_id=group_id,
        student_id=student_id,
        scroll_page=True
    )

@teacher_bp.post("/student/<int:student_id>/rename")
def rename_student(student_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    row = db_query_one("""
        SELECT s.group_id
        FROM students s
        JOIN `groups` g ON g.id = s.group_id
        WHERE s.id = :sid AND g.teacher_id = :tid
    """, {"sid": student_id, "tid": teacher_id})

    if not row:
        flash("Leerling niet gevonden.", "danger")
        return redirect(url_for("teacher.dashboard"))

    new_name = (request.form.get("new_name") or "").strip()
    if not new_name:
        flash("Naam mag niet leeg zijn.", "warning")
        return redirect(url_for("teacher.student", student_id=student_id))

    try:
        db_execute(
            "UPDATE students SET username=:name WHERE id=:sid",
            {"name": new_name, "sid": student_id}
        )
        flash("Naam succesvol gewijzigd.", "success")
    except Exception:
        flash("Naam wijzigen mislukt. Mogelijk bestaat deze naam al in de groep.", "danger")

    return redirect(url_for("teacher.student", student_id=student_id))


@teacher_bp.post("/student/<int:student_id>/delete")
def delete_student(student_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))
    
    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]


    # security: only allow deleting students that belong to THIS teacher
    row = db_query_one("""
        SELECT s.group_id
        FROM students s
        JOIN `groups` g ON g.id = s.group_id
        WHERE s.id = :sid AND g.teacher_id = :tid
    """, {"sid": student_id, "tid": teacher_id})

    if not row:
        flash("Je mag deze leerling niet verwijderen.", "danger")
        return redirect(url_for("teacher.dashboard"))

    group_id = row[0]

    # deleting the student cascades to exercises, points, puzzle pieces, etc.
    db_execute("DELETE FROM students WHERE id = :sid", {"sid": student_id})

    flash("Leerling verwijderd.", "success")
    return redirect(url_for("teacher.group", group_id=group_id))

@teacher_bp.route("/student/<int:student_id>/reset", methods=["POST"])
def reset_sequence_student(student_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        "SELECT id FROM teachers WHERE username=:u",
        {"u": session["username"]}
    )[0]

    row = db_query_one("""
        SELECT s.group_id
        FROM students s
        JOIN `groups` g ON g.id = s.group_id
        WHERE s.id = :sid AND g.teacher_id = :tid
    """, {"sid": student_id, "tid": teacher_id})

    if not row:
        flash("Je mag deze leerling niet verwijderen.", "danger")
        return redirect(url_for("teacher.dashboard"))
    
    group_id = row[0]

    # Reset every student in group to step 1
    db_execute("""
        UPDATE students
        SET current_step = 1
        WHERE group_id = :gid
            AND id = :sid
    """, {"gid": group_id, "sid": student_id} )

    flash("Leerling opnieuw gestart vanaf stap 1.", "success")
    return redirect(url_for("teacher.group", group_id=group_id))

@teacher_bp.route("/group/<int:group_id>/print")
def print_group_cards(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    g_row = db_query_one(
        'SELECT name, activation_code FROM `groups` WHERE id=:gid',
        {'gid': group_id}
    )
    if not g_row:
        flash("Groep bestaat niet.", "danger")
        return redirect(url_for('teacher.dashboard'))

    group_name, activation_code = g_row

    rows = db_query_all('''
        SELECT username, pin
        FROM students
        WHERE group_id=:gid
        ORDER BY username
    ''', {'gid': group_id})

    students = [(r[0], r[1], pin_to_animals(r[1])) for r in rows]

    return render_template(
        "teacher_group_print.html",
        group_id=group_id,
        group_name=group_name,
        activation_code=activation_code,
        students=students,
        scroll_page=True
    )


@teacher_bp.route("/group/<int:group_id>/preview")
def preview_group_exercise(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    step_id = request.args.get("step_id", type=int)

    gs = load_preview_settings_for_group(group_id, step_id)

    preview = build_preview_exercise(group_id, gs)

    if preview is None:
        flash("Geen voorbeeldopgave mogelijk met deze instellingen.", "warning")
        return redirect(url_for('teacher.group', group_id=group_id))

    return render_template(
        "preview.html",
        group_id=group_id,
        preview=preview,
        settings=gs,
        step_id=step_id
    )


# -----------------------------
# EXPORT GROUP CSV
# -----------------------------
@teacher_bp.route("/group/<int:group_id>/export.csv")
def export_group_csv(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    g_row = db_query_one(
        'SELECT name FROM `groups` WHERE id=:gid',
        {'gid': group_id}
    )
    if not g_row:
        flash("Groep bestaat niet.", "danger")
        return redirect(url_for('teacher.dashboard'))

    group_name = g_row[0]

    rows = db_query_all('''
        SELECT
          u.username, e.set_id, e.operation, e.a, e.b,
          e.user_answer, e.correct_answer, e.is_correct,
          e.response_time, e.timestamp, e.difficulty,
          e.show_timer, e.meta_self_score, e.time_self_score, e.time_feedback, e.current_elo, e.delta_elo, e.current_difficulty_zone
        FROM exercises e
        JOIN students u ON u.id = e.student_id
        WHERE u.group_id=:gid
        ORDER BY u.username, e.set_id, e.id
    ''', {'gid': group_id})

    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow([
        'username', 'set_id', 'operation', 'a', 'b',
        'user_answer', 'correct_answer', 'is_correct',
        'response_time_exercies', 'exercise_timestamp',
        'exercise_difficulty', 'show_timer',
        'confidence', 'calibratation_of_confidence',
        'response_time_self_score', 'response_time_feedback', 
        'current_elo', 'delta_elo', 'current_difficulty_zone'
    ])
    

    for r in rows:
        r = list(r)
        if r[9] is not None and hasattr(r[9], 'isoformat'):
            r[9] = r[9].isoformat(sep=' ')
        if r[12] != 0:
            self_score = r[12]
            is_correct = r[7]
            if (self_score == 4 and is_correct) or (self_score == 1 and not is_correct):
                r.insert(13, 3)
            elif (self_score == 3 and is_correct) or (self_score == 2 and not is_correct):
                r.insert(13, 2)
            elif (self_score == 2 and is_correct) or (self_score == 3 and not is_correct):
                r.insert(13, 1)
            else:
                r.insert(13, 0)
        else:
            r.insert(13, None)
        writer.writerow(r)

    csv_text = output.getvalue()
    output.close()

    filename = f"group_{group_name}_export.csv".replace(" ", "_")
    bom = '\ufeff'

    return Response(
        bom + csv_text,
        mimetype='text/csv; charset=utf-8',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# -----------------------------
# EXPORT GROUP SETTINGS
# -----------------------------
@teacher_bp.route("/group/<int:group_id>/export_settings.json")
def export_group_settings(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    g_row = db_query_one('''
        SELECT name,
            allow_timer_choice, fixed_show_timer,
            difficulty_choice, fixed_difficulty,
            operation_add_visible, operation_multiply_visible,
            operation_negation_visible, operation_mix_visible,
            mix_add, mix_multiply, mix_negation,
            questions_per_set, meta_prompt_mode,
            fixation_screen, demo_metacognition, research_mode,
            avoid_duplicate_pairs, avoid_duplicate_answers,
            treat_symmetric_as_duplicates, avoid_tie_problems,
            operand_position_counterbalancing,
            excluded_a, excluded_b, excluded_answers
        FROM `groups` WHERE id=:gid
    ''', {'gid': group_id})

    if not g_row:
        flash("Groep niet gevonden.", "danger")
        return redirect(url_for('teacher.dashboard'))

    payload = {
        "version": 1,
        "source_group": g_row[0],
        "settings": {
            "allow_timer_choice": bool(g_row[1]),
            "fixed_show_timer": bool(g_row[2]),
            "difficulty_choice": int(g_row[3]),
            "fixed_difficulty": int(g_row[4]),
            "operation_add_visible": bool(g_row[5]),
            "operation_multiply_visible": bool(g_row[6]),
            "operation_negation_visible": bool(g_row[7]),
            "operation_mix_visible": bool(g_row[8]),
            "mix_add": bool(g_row[9]),
            "mix_multiply": bool(g_row[10]),
            "mix_negation": bool(g_row[11]),
            "questions_per_set": g_row[12] or 10,
            "meta_prompt_mode": g_row[13] if g_row[13] is not None else 1,
            "fixation_screen": bool(g_row[14]),
            "demo_metacognition": bool(g_row[15]),
            "research_mode": bool(g_row[16]),
            "avoid_duplicate_pairs": bool(g_row[17]),
            "avoid_duplicate_answers": bool(g_row[18]),
            "treat_symmetric_as_duplicates": bool(g_row[19]),
            "avoid_tie_problems": bool(g_row[20]),
            "operand_position_counterbalancing": bool(g_row[21]),
            "excluded_a": g_row[22] or '',
            "excluded_b": g_row[23] or '',
            "excluded_answers": g_row[24] or '',
        }
    }

    # Include sequence steps if there is an active sequence
    step_rows = db_query_all('''
        SELECT s.position,
               s.questions_per_set, s.meta_prompt_mode,
               s.allow_timer_choice, s.fixed_show_timer,
               s.difficulty_choice, s.fixed_difficulty,
               s.operation_add_visible, s.operation_multiply_visible,
               s.operation_negation_visible, s.operation_mix_visible,
               s.mix_add, s.mix_multiply, s.mix_negation
        FROM exercise_sequence_steps s
        JOIN exercise_sequences seq ON seq.id = s.sequence_id
        WHERE seq.group_id=:gid
        ORDER BY s.position
    ''', {'gid': group_id})
    print("step", step_rows)

    if step_rows:
        payload["sequence"] = [
            {
                "position": r[0],
                "questions_per_set": r[1],
                "meta_prompt_mode": r[2],
                "allow_timer_choice": bool(r[3]),
                "fixed_show_timer": bool(r[4]),
                "difficulty_choice": int(r[5]),
                "fixed_difficulty": int(r[6]),
                "operation_add_visible": bool(r[7]),
                "operation_multiply_visible": bool(r[8]),
                "operation_negation_visible": bool(r[9]),
                "operation_mix_visible": bool(r[10]),
                "mix_add": bool(r[11]),
                "mix_multiply": bool(r[12]),
                "mix_negation": bool(r[13]),
            }
            for r in step_rows
        ]

    filename = f"instellingen_{g_row[0]}.json".replace(" ", "_")
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# -----------------------------
# IMPORT GROUP SETTINGS
# -----------------------------
@teacher_bp.route("/group/<int:group_id>/import_settings", methods=["POST"])
def import_group_settings(group_id):
    if 'username' not in session or session.get('role') != 'teacher':
        return redirect(url_for('auth.login_teacher'))

    teacher_id = db_query_one(
        'SELECT id FROM teachers WHERE username=:u',
        {'u': session['username']}
    )[0]

    if not teacher_owns_group(teacher_id, group_id):
        flash("Geen toegang!", "danger")
        return redirect(url_for('teacher.dashboard'))

    uploaded = request.files.get("settings_file")
    if not uploaded:
        flash("Geen bestand geselecteerd.", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    try:
        data = json.loads(uploaded.stream.read().decode('utf-8'))
    except Exception:
        flash("Ongeldig bestand. Upload een geldig JSON-instellingenbestand.", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    if data.get("version") != 1 or "settings" not in data:
        flash("Ongeldig instellingenbestand (verkeerde versie of formaat).", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    s = data["settings"]
    imported_steps = data.get("sequence") or []

    def _bool(src, key, default=False):
        return 1 if src.get(key, default) else 0

    def _int(src, key, default=0):
        try:
            return int(src.get(key, default))
        except (ValueError, TypeError):
            return default

    # Parse research + group-level settings from the file
    fixation_screen              = _bool(s, "fixation_screen")
    demo_metacognition           = _bool(s, "demo_metacognition")
    research_mode                = _bool(s, "research_mode")
    avoid_duplicate_pairs        = _bool(s, "avoid_duplicate_pairs")
    avoid_duplicate_answers      = _bool(s, "avoid_duplicate_answers")
    treat_symmetric_as_duplicates = _bool(s, "treat_symmetric_as_duplicates")
    avoid_tie_problems           = _bool(s, "avoid_tie_problems")
    operand_position_counterbalancing = _bool(s, "operand_position_counterbalancing")
    excluded_a       = str(s.get("excluded_a") or '').strip()
    excluded_b       = str(s.get("excluded_b") or '').strip()
    excluded_answers = str(s.get("excluded_answers") or '').strip()

    allow_timer_choice       = _bool(s, "allow_timer_choice", True)
    fixed_show_timer         = _bool(s, "fixed_show_timer", True)
    difficulty_choice        = _int(s, "difficulty_choice", 0)
    fixed_difficulty         = _int(s, "fixed_difficulty", 2)
    questions_per_set        = _int(s, "questions_per_set", 10)
    meta_prompt_mode         = _int(s, "meta_prompt_mode", 1)
    operation_add_visible    = _bool(s, "operation_add_visible", True)
    operation_multiply_visible = _bool(s, "operation_multiply_visible", True)
    operation_negation_visible = _bool(s, "operation_negation_visible", True)
    operation_mix_visible    = _bool(s, "operation_mix_visible", True)
    mix_add      = _bool(s, "mix_add", True)
    mix_multiply = _bool(s, "mix_multiply", True)
    mix_negation = _bool(s, "mix_negation", True)

    new_research_settings = {
        'fixation_screen': fixation_screen,
        'demo_metacognition': demo_metacognition,
        'research_mode': research_mode,
        'avoid_duplicate_pairs': avoid_duplicate_pairs,
        'avoid_duplicate_answers': avoid_duplicate_answers,
        'treat_symmetric_as_duplicates': treat_symmetric_as_duplicates,
        'avoid_tie_problems': avoid_tie_problems,
        'operand_position_counterbalancing': operand_position_counterbalancing,
        'excluded_a': excluded_a,
        'excluded_b': excluded_b,
        'excluded_answers': excluded_answers,
    }

    # --- Case A: file contains sequence steps ---
    if imported_steps:
        # Validate every step against the research settings from the file
        for i, step in enumerate(imported_steps, start=1):
            step_settings = {
                'questions_per_set': _int(step, "questions_per_set", 10),
                'difficulty_choice': _int(step, "difficulty_choice", 0),
                'fixed_difficulty': _int(step, "fixed_difficulty", 2),
                'operation_add_visible': _bool(step, "operation_add_visible", True),
                'operation_multiply_visible': _bool(step, "operation_multiply_visible", True),
                'operation_negation_visible': _bool(step, "operation_negation_visible", True),
                'operation_mix_visible': _bool(step, "operation_mix_visible", True),
                'mix_add': _bool(step, "mix_add", True),
                'mix_multiply': _bool(step, "mix_multiply", True),
                'mix_negation': _bool(step, "mix_negation", True),
            }
            ops_sum = (step_settings['operation_add_visible'] +
                       step_settings['operation_multiply_visible'] +
                       step_settings['operation_negation_visible'] +
                       step_settings['operation_mix_visible'])
            if ops_sum == 0:
                flash(f"Importeren mislukt! Stap {i} heeft geen operaties.", "danger")
                return redirect(url_for('teacher.group', group_id=group_id))
            if step_settings['operation_mix_visible'] and (
                    step_settings['mix_add'] + step_settings['mix_multiply'] + step_settings['mix_negation'] == 0):
                flash(f"Importeren mislukt! Mix in stap {i} heeft geen operaties.", "danger")
                return redirect(url_for('teacher.group', group_id=group_id))
            validation_settings = build_validation_settings(step_settings, new_research_settings)
            error_msg = validate_group_settings(validation_settings)
            if error_msg:
                flash(f"Importeren mislukt! Stap {i}: {error_msg}", "danger")
                return redirect(url_for('teacher.group', group_id=group_id))

        # Save research settings to the group
        db_execute('''
            UPDATE `groups`
            SET fixation_screen=:fix,
                demo_metacognition=:demo,
                research_mode=:rm,
                avoid_duplicate_pairs=:adp,
                avoid_duplicate_answers=:ada,
                treat_symmetric_as_duplicates=:tsd,
                avoid_tie_problems=:atp,
                operand_position_counterbalancing=:opc,
                excluded_a=:ea,
                excluded_b=:eb,
                excluded_answers=:eans
            WHERE id=:gid
        ''', {
            'fix': fixation_screen, 'demo': demo_metacognition, 'rm': research_mode,
            'adp': avoid_duplicate_pairs, 'ada': avoid_duplicate_answers,
            'tsd': treat_symmetric_as_duplicates, 'atp': avoid_tie_problems,
            'opc': operand_position_counterbalancing,
            'ea': excluded_a, 'eb': excluded_b, 'eans': excluded_answers,
            'gid': group_id,
        })

        # Replace the sequence steps
        sequence_id = get_or_create_sequence_for_group(group_id)
        db_execute('DELETE FROM exercise_sequence_steps WHERE sequence_id=:sid',
                   {'sid': sequence_id})

        for step in imported_steps:
            db_execute('''
                INSERT INTO exercise_sequence_steps (
                    sequence_id, position,
                    questions_per_set, meta_prompt_mode,
                    allow_timer_choice, fixed_show_timer,
                    difficulty_choice, fixed_difficulty,
                    operation_add_visible, operation_multiply_visible,
                    operation_negation_visible, operation_mix_visible,
                    mix_add, mix_multiply, mix_negation
                ) VALUES (
                    :sid, :pos,
                    :qps, :mpm,
                    :at, :fst,
                    :dc, :fd,
                    :oav, :omv, :onv, :oxv,
                    :ma, :mm, :mn
                )
            ''', {
                'sid': sequence_id,
                'pos': _int(step, "position", 1),
                'qps': _int(step, "questions_per_set", 10),
                'mpm': _int(step, "meta_prompt_mode", 1),
                'at':  _bool(step, "allow_timer_choice", True),
                'fst': _bool(step, "fixed_show_timer", True),
                'dc':  _int(step, "difficulty_choice", 0),
                'fd':  _int(step, "fixed_difficulty", 2),
                'oav': _bool(step, "operation_add_visible", True),
                'omv': _bool(step, "operation_multiply_visible", True),
                'onv': _bool(step, "operation_negation_visible", True),
                'oxv': _bool(step, "operation_mix_visible", True),
                'ma':  _bool(step, "mix_add", True),
                'mm':  _bool(step, "mix_multiply", True),
                'mn':  _bool(step, "mix_negation", True),
            })

        # Reset all students to step 1 since the sequence changed
        db_execute('UPDATE students SET current_step=1 WHERE group_id=:gid', {'gid': group_id})

        first = imported_steps[0]
        first_step_settings = {
            'questions_per_set': _int(first, "questions_per_set", 10),
            'operation_add_visible': _bool(first, "operation_add_visible", True),
            'operation_multiply_visible': _bool(first, "operation_multiply_visible", True),
            'operation_negation_visible': _bool(first, "operation_negation_visible", True),
            'operation_mix_visible': _bool(first, "operation_mix_visible", True),
            'mix_add': _bool(first, "mix_add", True),
            'mix_multiply': _bool(first, "mix_multiply", True),
            'mix_negation': _bool(first, "mix_negation", True),
            'difficulty_choice': _int(first, "difficulty_choice", 0),
            'fixed_difficulty': _int(first, "fixed_difficulty", 2),
        }
        build_group_pools(group_id, build_validation_settings(first_step_settings, new_research_settings))

        flash("Instellingen en oefenreeks succesvol geïmporteerd. Alle leerlingen starten opnieuw vanaf stap 1.", "success")
        return redirect(url_for('teacher.group', group_id=group_id))

    # --- Case B: no sequence in file — apply full group settings ---
    
    group_step_settings = {
        'questions_per_set': questions_per_set,
        'operation_add_visible': operation_add_visible,
        'operation_multiply_visible': operation_multiply_visible,
        'operation_negation_visible': operation_negation_visible,
        'operation_mix_visible': operation_mix_visible,
        'mix_add': mix_add,
        'mix_multiply': mix_multiply,
        'mix_negation': mix_negation,
        'difficulty_choice': difficulty_choice,
        'fixed_difficulty': fixed_difficulty,
    }

    if operation_add_visible + operation_multiply_visible + operation_negation_visible + operation_mix_visible == 0:
        flash("Importeren mislukt! Er moet minstens 1 operatie beschikbaar zijn.", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    if mix_add + mix_multiply + mix_negation == 0 and operation_mix_visible:
        flash("Importeren mislukt! Mix moet minstens 1 operatie bevatten.", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    validation_settings = build_validation_settings(group_step_settings, new_research_settings)
    error_msg = validate_group_settings(validation_settings)
    if error_msg:
        flash(f"Importeren mislukt! {error_msg}", "danger")
        return redirect(url_for('teacher.group', group_id=group_id))

    db_execute('''
        UPDATE `groups`
        SET allow_timer_choice=:at,
            fixed_show_timer=:fst,
            difficulty_choice=:dc,
            fixed_difficulty=:fd,
            operation_add_visible=:oav,
            operation_multiply_visible=:omv,
            operation_negation_visible=:onv,
            operation_mix_visible=:oxv,
            mix_add=:ma,
            mix_multiply=:mm,
            mix_negation=:mn,
            questions_per_set=:qps,
            meta_prompt_mode=:mpm,
            fixation_screen=:fix,
            demo_metacognition=:demo,
            research_mode=:rm,
            avoid_duplicate_pairs=:adp,
            avoid_duplicate_answers=:ada,
            treat_symmetric_as_duplicates=:tsd,
            avoid_tie_problems=:atp,
            operand_position_counterbalancing=:opc,
            excluded_a=:ea,
            excluded_b=:eb,
            excluded_answers=:eans
        WHERE id=:gid
    ''', {
        'at': allow_timer_choice,
        'fst': fixed_show_timer,
        'dc': difficulty_choice,
        'fd': fixed_difficulty,
        'oav': operation_add_visible,
        'omv': operation_multiply_visible,
        'onv': operation_negation_visible,
        'oxv': operation_mix_visible,
        'ma': mix_add,
        'mm': mix_multiply,
        'mn': mix_negation,
        'qps': questions_per_set,
        'mpm': meta_prompt_mode,
        'fix': fixation_screen,
        'demo': demo_metacognition,
        'rm': research_mode,
        'adp': avoid_duplicate_pairs,
        'ada': avoid_duplicate_answers,
        'tsd': treat_symmetric_as_duplicates,
        'atp': avoid_tie_problems,
        'opc': operand_position_counterbalancing,
        'ea': excluded_a,
        'eb': excluded_b,
        'eans': excluded_answers,
        'gid': group_id,
    })

    build_group_pools(group_id, build_validation_settings(group_step_settings, new_research_settings))

    flash("Instellingen succesvol geïmporteerd en opgeslagen.", "success")
    return redirect(url_for('teacher.group', group_id=group_id))
