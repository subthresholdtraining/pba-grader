"""
Test the grading logic against known submissions.
"""

import sys
sys.path.insert(0, '.')

from grading_logic import grade_submission, determine_overall_grade, parse_duration

# Test Lara Sullivan's submission
lara_answers = {
    'q1': '30 seconds',
    'q2': '35 seconds',
    'q3': '40 seconds',
    'q4': 'DOOR',
    'q5': 'Door',
    'q6': '5 seconds',
    'q7': '6 seconds',
    'q8': 'Guideline is 5% - 10%. I would opt for 10% since she\'s been doing well.',
    'q9': '3:20',
    'q10': '3:40',
    'q11': '3:20',
    'q12': 'Decrease the target duration',
    'q13': '1:25',
    'q13b': '8-10 warm ups',
    'q14': '1:35',
    'q14b': '5-8 steps',
    'q15': '1:54',
    'q15b': '5-8 steps',
    'q16': 'reduce the intensity of them turning on the car engine by parking their car further down the street and begin the Car is a bore training at step 7',
    'q17': '1 rep of steps 1 & 2'
}

# Expected results from Amanda's grading
lara_expected = {
    'q1': False,  # INCORRECT - 30 sec is too high
    'q2': True,   # CORRECT - ~17% increase
    'q3': True,   # CORRECT
    'q4': True,   # CORRECT
    'q5': True,   # CORRECT
    'q6': True,   # CORRECT
    'q7': True,   # CORRECT
    'q8': False,  # INCORRECT - should push higher
    'q9': False,  # INCORRECT - too conservative
    'q10': True,  # CORRECT with ECF
    'q11': True,  # CORRECT
    'q12': True,  # CORRECT
    'q13': False, # INCORRECT - too conservative
    'q13b': False, # INCORRECT - too many warmups
    'q14': True,  # CORRECT
    'q14b': True, # CORRECT
    'q15': True,  # CORRECT
    'q15b': True, # CORRECT
    'q16': True,  # CORRECT
    'q17': True,  # CORRECT
}

print("=" * 60)
print("Testing Lara Sullivan's Submission")
print("=" * 60)

results = grade_submission(lara_answers)

matches = 0
mismatches = 0

for q_id, expected in lara_expected.items():
    actual = results[q_id].is_correct
    status = "✓" if actual == expected else "✗"
    if actual == expected:
        matches += 1
    else:
        mismatches += 1

    print(f"{q_id}: Expected {expected}, Got {actual} {status}")
    if actual != expected:
        print(f"   Feedback: {results[q_id].feedback[:80]}...")
        if results[q_id].calculation:
            print(f"   Calc: {results[q_id].calculation}")

print()
print(f"Matches: {matches}/{len(lara_expected)}")
print(f"Mismatches: {mismatches}/{len(lara_expected)}")

overall_grade, resubmit = determine_overall_grade(results)
print(f"\nOverall Grade: {overall_grade}")
print(f"Questions to resubmit: {[q for q, _ in resubmit]}")

# Test Monica Falcon's submission
print("\n" + "=" * 60)
print("Testing Monica Falcon's Submission")
print("=" * 60)

monica_answers = {
    'q1': '10 seconds',
    'q2': '15 seconds',
    'q3': '20 seconds',
    'q4': 'Door is a bore',
    'q5': 'Door',
    'q6': '3 seconds absence',
    'q7': '5 seconds',
    'q8': '8 minutes and 8 seconds',
    'q9': '5 minutes and 30 seconds',
    'q10': '5:45',
    'q11': '5:30',
    'q12': 'Key is a bore',
    'q13': '2:45',
    'q13b': '5',
    'q14': '2:00',
    'q14b': '4',
    'q15': '2:30',
    'q15b': '4',
    'q16': 'Open the car, get in, close door, sit in car for 10 seconds.',
    'q17': '5 repetitions of step 1 and 2'
}

# Expected from Amanda's grading
monica_expected = {
    'q1': True,   # CORRECT
    'q2': False,  # INCORRECT - 50% increase too high
    'q3': False,  # INCORRECT - 33% increase too high
    'q4': True,   # CORRECT
    'q5': True,   # CORRECT
    'q6': True,   # CORRECT (Amanda accepted 3 sec)
    'q7': True,   # CORRECT
    'q8': False,  # INCORRECT
    'q9': True,   # CORRECT
    'q10': True,  # CORRECT (Amanda accepted ~4.5%)
    'q11': True,  # CORRECT
    'q12': False, # INCORRECT
    'q13': True,  # CORRECT
    'q13b': True, # CORRECT
    'q14': False, # INCORRECT - decreased when should push
    'q14b': True, # CORRECT
    'q15': False, # INCORRECT - too high increase
    'q15b': True, # CORRECT
    'q16': True,  # CORRECT (Amanda accepted it)
    'q17': False, # INCORRECT - too many reps
}

results = grade_submission(monica_answers)

matches = 0
mismatches = 0

for q_id, expected in monica_expected.items():
    actual = results[q_id].is_correct
    status = "✓" if actual == expected else "✗"
    if actual == expected:
        matches += 1
    else:
        mismatches += 1

    print(f"{q_id}: Expected {expected}, Got {actual} {status}")
    if actual != expected:
        print(f"   Feedback: {results[q_id].feedback[:80]}...")

print()
print(f"Matches: {matches}/{len(monica_expected)}")
print(f"Mismatches: {mismatches}/{len(monica_expected)}")

overall_grade, resubmit = determine_overall_grade(results)
print(f"\nOverall Grade: {overall_grade}")
print(f"Questions to resubmit: {[q for q, _ in resubmit]}")

# Test duration parsing
print("\n" + "=" * 60)
print("Testing Duration Parser")
print("=" * 60)

test_cases = [
    ("30 seconds", 30),
    ("2 minutes", 120),
    ("2:45", 165),
    ("3'20\"", 200),
    ("5 minutes 30 seconds", 330),
    ("Door", None),
    ("DIAB", None),
    ("1.25", 1.25),  # Could be ambiguous
    ("1:25", 85),
]

for input_str, expected in test_cases:
    result = parse_duration(input_str)
    status = "✓" if result == expected else "✗"
    print(f"'{input_str}' -> {result} (expected {expected}) {status}")
