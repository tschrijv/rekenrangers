from flask import (
    Blueprint, render_template, request, redirect, url_for,
    session, flash, g
)
from flask_babel import gettext as _
from datetime import datetime
import random

from models.db import db_query_one, db_query_all, db_execute
from services.points import get_user_points, add_points
from services.difficulty import calculate_elo, get_difficulty_from_elo, get_zone_from_elo
from services.exercise_selector import (select_problem)


student_bp = Blueprint("student", __name__)


# -------------------------------
# Helpers
# -------------------------------

def build_mix_difficulty_sequence(n, max_run=2):
    """
    Build a difficulty sequence using 1,2,3 as equally as possible.
    Ensures no more than `max_run` identical difficulties in a row.
    """
    diffs = [1, 2, 3]

    base = n // 3
    rem = n % 3

    counts = {1: base, 2: base, 3: base}

    for d in random.sample(diffs, rem):
        counts[d] += 1

    plan = []

    def ok_to_place(d):
        if len(plan) < max_run:
            return True
        return not all(x == d for x in plan[-max_run:])

    remaining = counts.copy()

    for _ in range(n):
        candidates = [d for d in diffs if remaining[d] > 0 and ok_to_place(d)]

        if not candidates:
            break

        candidates.sort(key=lambda d: remaining[d], reverse=True)
        top = remaining[candidates[0]]
        top_candidates = [d for d in candidates if remaining[d] == top]

        choice = random.choice(top_candidates)

        plan.append(choice)
        remaining[choice] -= 1

    return plan

def build_mix_plan(ops, n, max_run=2, max_tries=200):
    """
    Balanced + no more than `max_run` identical ops in a row.
    Example n=10 ops=[add,multiply,negation] -> 4/3/3 distribution (shuffled).
    """
    ops = list(ops)
    k = len(ops)
    if k == 0 or n <= 0:
        return []
    if k == 1:
        # only one option: can't enforce no-3-in-a-row if n>2, but nothing else possible
        return [ops[0]] * n

    # target counts: as equal as possible
    base = n // k
    rem = n % k
    counts = {op: base for op in ops}
    # distribute remainder randomly to avoid always biasing same op
    for op in random.sample(ops, rem):
        counts[op] += 1

    def ok_to_place(plan, op):
        if len(plan) < max_run:
            return True
        return not all(x == op for x in plan[-max_run:])

    # greedy with restarts
    for _ in range(max_tries):
        remaining = counts.copy()
        plan = []
        for _i in range(n):
            # candidates with remaining > 0 and not violating run constraint
            candidates = [op for op in ops if remaining[op] > 0 and ok_to_place(plan, op)]
            if not candidates:
                break

            # prefer higher remaining (keeps balance), random tie-break
            candidates.sort(key=lambda op: remaining[op], reverse=True)
            top = remaining[candidates[0]]
            top_candidates = [op for op in candidates if remaining[op] == top]
            choice = random.choice(top_candidates)

            plan.append(choice)
            remaining[choice] -= 1

        if len(plan) == n:
            return plan

    # fallback: balanced list shuffled (may violate constraint in rare cases)
    flat = []
    for op, c in counts.items():
        flat.extend([op] * c)
    random.shuffle(flat)
    return flat

def get_sequence_status_for_student(student_id):
    """
    Geeft info over de sequence van de groep van deze leerling.
    Retourneert dict of None als er geen sequence is.
    """
    row = db_query_one('SELECT group_id, current_step FROM students WHERE id=:u', {'u': student_id})
    if not row or row[0] is None:
        return None

    group_id, current_step = row
    if not current_step:
        current_step = 1

    seq_row = db_query_one('SELECT id FROM exercise_sequences WHERE group_id=:g', {'g': group_id})
    if not seq_row:
        return None

    sequence_id = seq_row[0]

    total_steps_row = db_query_one(
        'SELECT COUNT(*) FROM exercise_sequence_steps WHERE sequence_id=:sid',
        {'sid': sequence_id}
    )
    total_steps = total_steps_row[0] if total_steps_row else 0
    if total_steps == 0:
        # Sequence zonder stappen = effectief geen sequence
        return None

    return {
        'group_id': group_id,
        'sequence_id': sequence_id,
        'current_step': current_step,
        'total_steps': total_steps
    }


def load_group_settings_for_user():
    student_id = session.get('student_id')
    row = db_query_one('SELECT group_id FROM students WHERE id=:u', {'u': student_id})

    if not row or row[0] is None:
        return {
            'questions_per_set': 10,
            'meta_prompt_mode': 1,
            'allow_timer_choice': True,
            'fixed_show_timer': True,
            'difficulty_choice': 0,
            'fixed_difficulty': 2,
            'operation_add_visible': True,
            'operation_multiply_visible': True,
            'operation_negation_visible': True,
            'operation_mix_visible': True,
            'mix_add': True,
            'mix_multiply': True,
            'mix_negation': True,
            'fixation_screen': False,
            'demo_metacognition': False,
            'research_mode': False,
            'avoid_duplicate_pairs': False,
            'avoid_duplicate_answers': False,
            'treat_symmetric_as_duplicates': False,
            'avoid_tie_problems': False,
            'operand_position_counterbalancing': False,
            'excluded_a': '',
            'excluded_b': '',
            'excluded_answers': ''
        }

    group_id = row[0]

    g_row = db_query_one('''
        SELECT
          questions_per_set, meta_prompt_mode,
          allow_timer_choice, fixed_show_timer,
          difficulty_choice, fixed_difficulty,
          operation_add_visible, operation_multiply_visible,
          operation_negation_visible, operation_mix_visible,
          mix_add, mix_multiply, mix_negation, fixation_screen, demo_metacognition, research_mode,
          avoid_duplicate_pairs, avoid_duplicate_answers, 
          treat_symmetric_as_duplicates, avoid_tie_problems, operand_position_counterbalancing,
          excluded_a, excluded_b, excluded_answers
        FROM `groups`
        WHERE id=:gid
    ''', {'gid': group_id})

    return {
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
    


def load_effective_settings_for_user():
    """
    Basis = groepsinstellingen (incl. onderzoeksregels).
    Als er een sequence-stap actief is, overschrijven we sommige velden
    (vragen per set, meta, timer, moeilijkheid, operaties).
    Voor de leerling blijft het select-scherm hetzelfde.
    """
    base = load_group_settings_for_user()

    student_id = session.get('student_id')
    if not student_id:
        return base

    seq = get_sequence_status_for_student(student_id)
    if not seq:
        return base  # geen sequence → gewoon groepsinstellingen

    # Als current_step groter is dan aantal stappen, is de reeks klaar.
    # Maar dat handelen we in select_exercise af; hier proberen we gewoon de step in te lezen.
    step_row = db_query_one('''
        SELECT
            questions_per_set, meta_prompt_mode,
            allow_timer_choice, fixed_show_timer,
            difficulty_choice, fixed_difficulty,
            operation_add_visible, operation_multiply_visible,
            operation_negation_visible, operation_mix_visible,
            mix_add, mix_multiply, mix_negation
        FROM exercise_sequence_steps
        WHERE sequence_id=:sid AND position=:pos
    ''', {'sid': seq['sequence_id'], 'pos': seq['current_step']})

    if not step_row:
        # als er geen geldige step is, val terug op groep
        return base

    # Override velden die per step gaan
    base.update({
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

    return base




def _advance_sequence_step_if_any(student_id):
    """
    Verhoog de current_step van de leerling binnen de sequence.
    Als de laatste stap is afgewerkt, wordt current_step = total_steps + 1.
    Geen UI, enkel backend-boekhouding.
    """
    seq = get_sequence_status_for_student(student_id)
    if not seq:
        return  # geen sequence

    current = seq['current_step']
    total = seq['total_steps']

    if current <= total:
        # laatste stap → spring naar total+1 = 'klaar'
        new_step = current + 1
        db_execute('UPDATE students SET current_step=:cs WHERE id=:u',
                   {'cs': new_step, 'u': student_id})



# -------------------------------
# STUDENT ROUTES
# -------------------------------



@student_bp.route('/select_exercise')
def select_exercise():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']

    gs = load_effective_settings_for_user()
    # Check of er een sequence is, en of die klaar is
    seq = get_sequence_status_for_student(student_id)
    if seq and seq['current_step'] > seq['total_steps']:
        # reeks is afgelopen → toon stop-scherm
        return render_template('sequence_end.html', research_mode=gs['research_mode'], show_points=True)

   
    visible_operations = {
        'add': gs['operation_add_visible'],
        'multiply': gs['operation_multiply_visible'],
        'negation': gs['operation_negation_visible'],
        'mix': gs['operation_mix_visible']
    }
    mix_contents = {
        'add': gs['mix_add'],
        'multiply': gs['mix_multiply'],
        'negation': gs['mix_negation']
    }

    return render_template(
        'select.html',
        allow_timer_choice=gs['allow_timer_choice'],
        fixed_show_timer=gs['fixed_show_timer'],
        difficulty_choice=gs['difficulty_choice'],
        fixed_difficulty=gs['fixed_difficulty'],
        meta_prompt_mode=gs['meta_prompt_mode'],
        research_mode=gs['research_mode'],
        visible_operations=visible_operations,
        mix_contents=mix_contents,
        show_points=True,
        scroll_page=True,
        seq=seq
    )



@student_bp.route('/exercise', methods=['GET', 'POST'])
def exercise():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']

    # ------------------------
    # START NEW SET?
    # ------------------------
    if 'set_id' not in session:
        row = db_query_one('SELECT COALESCE(MAX(set_id),0) FROM exercises')
        session['set_id'] = (row[0] if row else 0) + 1
        session['points_awarded'] = False
       
        
        gs = load_effective_settings_for_user()
        session['questions_per_set'] = gs['questions_per_set']
        session['meta_prompt_mode'] = gs['meta_prompt_mode']

        op_arg = request.args.get('operation')
        visible = {
            'add': gs['operation_add_visible'],
            'multiply': gs['operation_multiply_visible'],
            'negation': gs['operation_negation_visible'],
            'mix': gs['operation_mix_visible'],
        }

        if op_arg not in visible or not visible[op_arg]:
            session.pop('set_id', None)
            session.pop('points_awarded', None)
            flash(_("Ongeldige operatie!"), "danger")
            return redirect(url_for('student.select_exercise'))

        if op_arg == 'mix' and not (gs['mix_add'] or gs['mix_multiply'] or gs['mix_negation']):
            session.pop('set_id', None)
            session.pop('points_awarded', None)
            flash(_("Mix is leeg!"), "danger")
            return redirect(url_for('student.select_exercise'))

        session['operation'] = op_arg

        # difficulty logic
        difficulty = request.args.get('difficulty', type=int)
        print(difficulty)
        if gs['difficulty_choice'] == 2:
            pass
        else:
            difficulty = difficulty if difficulty in (1, 2, 3) else gs['fixed_difficulty']

        session['difficulty'] = difficulty
        session['show_timer'] = True if request.args.get('show_timer', 'yes') == 'yes' else False


        if gs['difficulty_choice'] == 0 and difficulty == 4:
            session['difficulty_plan'] = build_mix_difficulty_sequence(
                int(session['questions_per_set'])
            )


        # --- operand position counterbalancing plan (per set) ---
        session['operand_position_counterbalancing'] = gs['operand_position_counterbalancing']

        if session['operand_position_counterbalancing']:
            n = int(session['questions_per_set'])
            half = n // 2
            plan = (["left"] * half) + (["right"] * (n - half))
            random.shuffle(plan)
            session['maxpos_plan'] = plan
        else:
            session.pop('maxpos_plan', None)

        # Build mix plan once per set (balanced + no 3-in-a-row)
        session.pop('mix_plan', None)
        if op_arg == 'mix':
            mix_ops = []
            if gs['mix_add']:
                mix_ops.append('add')
            if gs['mix_multiply']:
                mix_ops.append('multiply')
            if gs['mix_negation']:
                mix_ops.append('negation')

            # should already be validated earlier, but keep safe
            if mix_ops:
                session['mix_plan'] = build_mix_plan(mix_ops, int(session['questions_per_set']), max_run=2)

        

    # ------------------------
    # GRADING / SUBMIT
    # ------------------------
    if request.method == 'POST':
        gs = load_effective_settings_for_user()
        a = int(request.form['a'])
        b = int(request.form['b'])
        operation = request.form['operation']
        difficulty = request.form['difficulty']
        raw_answer = request.form.get('answer')
        timed_out = request.form.get('timed_out', '0') == '1'

        if timed_out or raw_answer in (None, ''):
            answer = None
        else:
            answer = int(raw_answer)

        response_time = float(request.form.get('response_time', 0.0))
        correct = a + b if operation == 'add' else a * b if operation == 'multiply' else a - b
        is_correct = int(answer == correct) if answer is not None else 0

        student_id = session['student_id']

        if difficulty == 3:
            time_limit = 25
        elif difficulty == 2:
            time_limit = 20
        else:
            time_limit = 15

        if not session.get('elo_awarded', False):
            if gs['difficulty_choice'] == 2:
                current_elo = db_query_one(
                    'SELECT difficulty_elo FROM students WHERE id=:u',
                    {'u': student_id})[0]
                new_elo = calculate_elo(current_elo, bool(is_correct), response_time, time_limit)
                db_execute('UPDATE students SET difficulty_elo=:e WHERE id=:u',
                        {'e': new_elo, 'u': student_id})
                session['elo_awarded'] = True

        db_execute('''
            INSERT INTO exercises
            (student_id, set_id, operation, a, b, user_answer, correct_answer,
             is_correct, response_time, timestamp, difficulty, show_timer, meta_self_score, current_elo, delta_elo, current_difficulty_zone)
            VALUES (:uid, :sid, :op, :a, :b, :ua, :ca,
                    :ok, :rt, NOW(), :diff, :timer, 0, :ce, :de, :cdz)
        ''', {
            'uid': student_id,
            'sid': session['set_id'],
            'op': operation,
            'a': a,
            'b': b,
            'ua': answer,
            'ca': correct,
            'ok': is_correct,
            'rt': response_time,
            'diff': difficulty,
            'ce': current_elo if gs['difficulty_choice'] == 2 else None,
            'de': (new_elo - current_elo) if gs['difficulty_choice'] == 2 else None,
            'cdz': get_zone_from_elo(current_elo) if gs['difficulty_choice'] == 2 else None,
            'timer': 1 if session.get('show_timer', True) else 0
        })

        

        # For feedback:
        session['first_arg'] = a
        session['second_arg'] = b
        session['correct'] = correct
        session['answer'] = answer
        session['current_real_operation'] = operation

        cnt = db_query_one(
            'SELECT COUNT(*) FROM exercises WHERE student_id=:u AND set_id=:s',
            {'u': student_id, 's': session['set_id']}
        )[0]

        # We always decide here whether this was the final question of the set
        session['feedback_final'] = (cnt >= session['questions_per_set'])

        if session.get('meta_prompt_mode', 1) == 1 and not timed_out:
            session['pending_exercise_id'] = session['set_id']
            return redirect(url_for('student.selfscore_q'))
        

        # meta OFF: still show feedback (without metacognition block)
        return redirect(url_for('student.feedback'))


    # ------------------------
    # GET → generate new question
    # ------------------------
    session['start_time'] = datetime.now().isoformat()
    set_id = session['set_id']
    session['elo_awarded'] = False

    base_op = session.get('operation')
    if not base_op:
        _cleanup_set_session()
        return redirect(url_for('student.select_exercise'))
    gs = load_effective_settings_for_user()
    difficulty = session['difficulty']
    if gs['difficulty_choice'] == 2:
        row = db_query_one(
                'SELECT difficulty_elo FROM students WHERE id=:u',
                {'u': student_id}
        )
        elo = row[0] if row else 1000
        difficulty = get_difficulty_from_elo(elo)

    # If mix difficulty is active, override per-question
    if difficulty == 4 and session.get('difficulty_plan'):
        cnt_done = db_query_one(
            'SELECT COUNT(*) FROM exercises WHERE student_id=:u AND set_id=:s',
            {'u': student_id, 's': set_id}
        )[0]

        if cnt_done < len(session['difficulty_plan']):
            difficulty = session['difficulty_plan'][cnt_done]

        student_id = session['student_id']

    # choose operation for this question
    if base_op == 'mix':
        # how many questions already done in this set?
        cnt_done = db_query_one(
            'SELECT COUNT(*) FROM exercises WHERE student_id=:u AND set_id=:s',
            {'u': student_id, 's': session['set_id']}
        )[0]

        plan = session.get('mix_plan') or []
        if cnt_done < len(plan):
            operation = plan[cnt_done]
        else:
            # fallback (shouldn't happen)
            ops = []
            if gs['mix_add']:
                ops.append('add')
            if gs['mix_multiply']:
                ops.append('multiply')
            if gs['mix_negation']:
                ops.append('negation')
            operation = random.choice(ops) if ops else 'add'
    else:
        operation = base_op

    session['current_real_operation'] = operation

    # previous exercises
    prev = db_query_all('''
        SELECT a, b, correct_answer, operation
        FROM exercises
        WHERE student_id=:u AND set_id=:s
    ''', {'u': student_id, 's': set_id})
    
    used_pairs = {}
    used_answers = set()
    for a_old, b_old, ans_old, op_old in prev:
        used_answers.add(ans_old)
        used_pairs.setdefault(op_old, set()).add((a_old, b_old))

    group_id = db_query_one('SELECT group_id FROM students WHERE id=:u', {'u': student_id})[0]
    exercise = select_problem(operation, difficulty, gs,
                            used_pairs.get(operation, set()),
                            used_answers,
                            group_id)

    if exercise is None:
        flash(_("Geen oefeningen mogelijk met deze instellingen."), "danger")
        return redirect(url_for('student.select_exercise'))

    a = exercise["a"]
    b = exercise["b"]

    # --- apply operand position counterbalancing (display-time swap) ---
    if session.get('operand_position_counterbalancing') and session.get('maxpos_plan'):
        cnt_done = db_query_one(
            'SELECT COUNT(*) FROM exercises WHERE student_id=:u AND set_id=:s',
            {'u': student_id, 's': set_id}
        )[0]

        if cnt_done < len(session['maxpos_plan']):
            desired = session['maxpos_plan'][cnt_done]  # "left" or "right"

            # Only safe for commutative operations
            if operation in ("add", "multiply"):
                if desired == "left" and a < b:
                    a, b = b, a
                elif desired == "right" and a > b:
                    a, b = b, a

    if difficulty == 3:
        time_limit = 25
    elif difficulty == 2:
        time_limit = 20
    else:
        time_limit = 15
    

    return render_template(
        'exercise.html',
        a=a,
        b=b,
        operation=operation,
        difficulty=difficulty,
        fixation_screen=gs['fixation_screen'],
        research_mode=gs['research_mode'],
        mouse_locked=gs['research_mode'],
        time_limit=time_limit,
        show_points=True
    )



def _cleanup_set_session():
    for key in [
        'set_id', 'difficulty', 'operation', 'show_timer',
        'start_time', 'first_arg', 'second_arg',
        'correct', 'answer', 'current_real_operation', 'step_advanced', 'operand_position_counterbalancing', 'maxpos_plan', 'mix_plan', 'difficulty_plan'
    ]:
        session.pop(key, None)


@student_bp.route('/selfscore_q', methods=['GET', 'POST'])
def selfscore_q():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    if 'pending_exercise_id' not in session:
        return redirect(url_for('student.exercise'))

    if request.method == 'POST':
        score = int(request.form['self_score'])
        time_self_score = float(request.form.get('time_self_score', 0.0) or 0.0)
        student_id = session['student_id']

        db_execute('''
            UPDATE exercises
            SET meta_self_score=:s,
                time_self_score=:tss
            WHERE student_id=:uid AND set_id=:sid
            ORDER BY id DESC LIMIT 1
        ''', {
            's': score,
            'tss': time_self_score,
            'uid': student_id,
            'sid': session['set_id']
        })

        session['meta_answer'] = score
        return redirect(url_for('student.feedback'))
    research_mode = load_effective_settings_for_user().get('research_mode', False)

    return render_template('selfscore_q.html', show_points=True, research_mode=research_mode, mouse_locked=research_mode)


@student_bp.route('/feedback', methods=['GET', 'POST'])
def feedback():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    meta_ans = session.get('meta_answer')

    if 'first_arg' not in session or 'second_arg' not in session or 'correct' not in session or 'answer' not in session:
        return redirect(url_for('student.exercise'))

    a = session['first_arg']
    b = session['second_arg']
    op = session['current_real_operation']
    correct = session['correct']
    answer = session['answer']


    if request.method == 'POST':

        student_id = session['student_id']
        time_feedback = float(request.form.get('time_feedback', 0.0) or 0.0)

        db_execute('''
            UPDATE exercises
            SET time_feedback=:tf
            WHERE student_id=:uid AND set_id=:sid
            ORDER BY id DESC LIMIT 1
        ''', {
            'tf': time_feedback,
            'uid': student_id,
            'sid': session['set_id']
        })


        session.pop('pending_exercise_id', None)
        session.pop('meta_answer', None)
        session.pop('first_arg', None)
        session.pop('second_arg', None)
        session.pop('correct', None)
        session.pop('answer', None)
        session.pop('current_real_operation', None)

        if session.pop('feedback_final', False):
            session['last_set_id'] = session['set_id']
            _cleanup_set_session()
            return redirect(url_for('student.result'))

        return redirect(url_for('student.exercise'))

    research_mode = load_effective_settings_for_user().get('research_mode', False)

    return render_template(
        'feedback.html',
        meta_answer=meta_ans,
        a=a,
        b=b,
        operation=op,
        correct=correct,
        answer=answer,
        research_mode=research_mode,
        mouse_locked=research_mode, 
        show_points=True
    )


@student_bp.route('/result')
def result():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']
    last_set_id = session.pop('last_set_id', None)

    if not last_set_id:
        row = db_query_one(
            'SELECT MAX(set_id) FROM exercises WHERE student_id=:u',
            {'u': student_id}
        )
        last_set_id = row[0] if row else None

    if not last_set_id:
        return render_template('result.html',
                               total_correct=0,
                               total_questions=0,
                               show_points=True)

    rows = db_query_all('''
        SELECT is_correct, response_time
        FROM exercises
        WHERE student_id=:u AND set_id=:s
        ORDER BY id
    ''', {'u': student_id, 's': last_set_id})

    exercises = rows
    total_correct = sum(r[0] for r in exercises)
    avg_time = round(sum(r[1] for r in exercises) / len(exercises), 2)

    gs = load_effective_settings_for_user()

    

    # point awarding
    if not session.get('points_awarded', False):
        base_pts = 10
        correct_bonus = total_correct * 2
        time_bonus = max(0, int(30 - avg_time))
        total_award = base_pts + correct_bonus + time_bonus

        add_points(student_id, total_award)
        session['points_awarded'] = True
        g.user_points = get_user_points(student_id)


    # sequence-voortgang (onzichtbaar voor leerling)
    _advance_sequence_step_if_any(student_id)

    seq = get_sequence_status_for_student(student_id)
    if seq:
        seq = True

    return render_template(
        'result.html',
        total_correct=total_correct,
        total_questions=len(exercises),
        research_mode=gs['research_mode'],
        mouse_locked=True,
        sequence_active=seq,
        show_points=True,
    )


# -----------------------------------
# PUZZLES
# -----------------------------------

@student_bp.route('/puzzles')
def puzzles_list():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']
    puzzles = db_query_all('SELECT id, name, image_path, rows_count, cols_count FROM puzzles')

    result = []
    for pid, name, img, rows, cols in puzzles:
        total = rows * cols
        owned = db_query_one(
            'SELECT COUNT(*) FROM student_puzzle_pieces WHERE student_id=:u AND puzzle_id=:p',
            {'u': student_id, 'p': pid}
        )[0]
        result.append({
            'id': pid,
            'name': name,
            'image_path': img,
            'complete': owned >= total,
            'progress': int(owned / total * 100)
        })

    return render_template('puzzles_list.html', puzzles=result, show_points=True)


@student_bp.route('/puzzle/<int:puzzle_id>')
def puzzle(puzzle_id):
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']
    puzzle = db_query_one(
        'SELECT id, name, image_path, rows_count, cols_count, piece_cost FROM puzzles WHERE id=:p',
        {'p': puzzle_id}
    )

    if not puzzle:
        flash(_("Puzzel bestaat niet!"), "danger")
        return redirect(url_for('student.puzzles_list'))

    pid, name, img, rows, cols, cost = puzzle

    owned = db_query_all(
        'SELECT piece_index FROM student_puzzle_pieces WHERE student_id=:u AND puzzle_id=:p',
        {'u': student_id, 'p': puzzle_id}
    )
    owned_set = {r[0] for r in owned}
    complete = len(owned_set) >= rows * cols

    return render_template(
        'puzzle.html',
        puzzle_id=pid,
        name=name,
        image_path=img,
        rows=rows,
        cols=cols,
        owned_pieces=owned_set,
        cost=cost,
        current_points=get_user_points(student_id),
        puzzle_complete=complete,
        show_points=True,
        scroll_page=True
    )


@student_bp.route('/buy_piece/<int:puzzle_id>', methods=['POST'])
def buy_piece(puzzle_id):
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']
    puzzle = db_query_one(
        'SELECT rows_count, cols_count, piece_cost FROM puzzles WHERE id=:p',
        {'p': puzzle_id}
    )

    if not puzzle:
        flash(_("Puzzel bestaat niet!"), "danger")
        return redirect(url_for('student.puzzles_list'))

    rows, cols, cost = puzzle
    total = rows * cols

    owned = db_query_all(
        'SELECT piece_index FROM student_puzzle_pieces WHERE student_id=:u AND puzzle_id=:p',
        {'u': student_id, 'p': puzzle_id}
    )
    owned_set = {r[0] for r in owned}

    if len(owned_set) >= total:
        flash(_("Puzzel is al volledig!"), "danger")
        return redirect(url_for('student.puzzle', puzzle_id=puzzle_id))

    if get_user_points(student_id) < cost:
        flash(_("Niet genoeg punten!"), "danger")
        return redirect(url_for('student.puzzle', puzzle_id=puzzle_id))

    add_points(student_id, -cost)

    new_piece = random.choice(list(set(range(total)) - owned_set))

    db_execute('''
        INSERT INTO student_puzzle_pieces (student_id, puzzle_id, piece_index)
        VALUES (:u, :p, :idx)
    ''', {'u': student_id, 'p': puzzle_id, 'idx': new_piece})

    return redirect(url_for('student.puzzle', puzzle_id=puzzle_id))


@student_bp.route('/reset_puzzle/<int:puzzle_id>', methods=['POST'])
def reset_puzzle(puzzle_id):
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    student_id = session['student_id']
    db_execute('DELETE FROM student_puzzle_pieces WHERE student_id=:u AND puzzle_id=:p',
               {'u': student_id, 'p': puzzle_id})

    flash(_("Puzzel is gereset!"), "warning")
    return redirect(url_for('student.puzzle', puzzle_id=puzzle_id))

# -----------------------------------
# DEMO
# -----------------------------------

@student_bp.route('/demo/start')
def demo_start():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    # start demo mode
    session['demo_mode'] = True
    session['demo_step'] = 1
    session['demo_metacognition'] = load_group_settings_for_user().get('demo_metacognition', False)
    session.pop('demo_lion_bought', None)
    

    return render_template(
            "demo_select.html",
            demo_audio="1.Startscherm.mp3",
            meta_prompt_mode=int(bool(session.get("demo_metacognition", False))),
            show_points=True
        )

@student_bp.post('/demo/next')
def demo_next():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    if not session.get('demo_mode'):
        return redirect(url_for('student.select_exercise'))

    session['demo_step'] = int(session.get('demo_step', 1)) + 1
    return redirect(url_for('student.demo_step'))
    
@student_bp.get('/demo/step')
def demo_step():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    if not session.get('demo_mode'):
        return redirect(url_for('student.select_exercise'))

    step = int(session.get('demo_step', 1))
    meta = bool(session.get('demo_metacognition', False))

    if step == 4 and not meta:
        session['demo_step'] = 5
        return redirect(url_for('student.demo_step'))

    if step == 2:
        return render_template(
            "demo_numpad.html",
            demo_audio = "2.1 Scherm met toetsenbord.mp3",
            show_points=True
        )

    elif step == 3:
        return render_template(
            "demo_exercise.html",
            demo_audio="Rekenoefening.mp3",
            show_points=True
        )
    
    elif step == 5:
        return render_template(
            "demo_too_late.html",
            demo_audio="4.mp3",
            show_points=True
        )

    elif (step == 4 and meta):
        return render_template(
            "demo_selfscore.html",
            demo_audio = "3.1 Metacognitiescherm.mp3",
            show_points=True
        )
    
    elif (step == 6 and meta):
        return render_template(
            "demo_meta_feedback.html",
            demo_audio = "5.1.mp3",
            show_points=True
        )
    
    elif (step == 6 and not meta):
        return render_template(
            "demo_feedback.html",
            demo_audio = "5.2.mp3",
            show_points=True
        )

    elif step == 7:
        return render_template(
            "demo_result.html",
            demo_audio="6.mp3",
            total_correct=1,
            total_questions=1,
            show_points=True
        )


    elif step == 8:
        return render_template(
            "demo_end_sequence.html",
            demo_audio = "7.mp3",
            show_points=True
        )

    elif step == 9:
        return render_template(
            "demo_puzzles_list.html",
            demo_audio="Audio 8_Nieuw.mp3",
            show_points=True,
            scroll_page=True
        )

    elif step == 10:
        return render_template(
            "demo_puzzle_fake.html",
            demo_audio = "9.mp3",
            show_points=False,
            scroll_page=True
        )
    
    elif step == 11:
        return render_template(
            "demo_end.html",
            demo_audio = "10.mp3",
            show_points=False
        )

    # fallback
    return redirect(url_for('student.demo_exit'))
    
@student_bp.route('/demo/buy-lion-piece', methods=['POST'])
def demo_buy_lion_piece():
    if not session.get('demo_mode'):
        return redirect(url_for('student.select_exercise'))

    session['demo_lion_bought'] = True

    # Stay on the same demo puzzle page
    return render_template(
            "demo_puzzle_fake.html",
            show_points=True,
            scroll_page =True)


@student_bp.post('/demo/exit')
def demo_exit():
    if 'student_id' not in session:
        return redirect(url_for('auth.index'))

    # stop demo, but don't mark demo_seen yet
    session.pop('demo_mode', None)
    session.pop('demo_step', None)
    session.pop('demo_metacognition', None)

    db_execute(
        "UPDATE students SET demo_seen = 1 WHERE id = :id",
        {"id": session.get('student_id')}
    )



    return redirect(url_for('student.select_exercise'))



# -----------------------------------
# BEFORE REQUEST — student points
# -----------------------------------

@student_bp.before_app_request
def load_user_points():
    g.user_points = 0

    if 'student_id' not in session:
        return

    student_id = session['student_id']
    row = db_query_one('SELECT id FROM students WHERE id=:u', {'u': student_id})

    if not row:
        session.clear()
        return redirect(url_for('auth.index'))

    g.user_points = get_user_points(student_id)

    
