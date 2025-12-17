"""
PBA Grading Logic Module
Contains all the grading rules and feedback templates for the Plan Building Assignment.
"""

import re
from dataclasses import dataclass
from typing import Optional, Tuple

# Import anthropic for LLM normalization (optional dependency)
try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def normalize_duration_with_llm(raw_answer: str, api_key: str) -> str:
    """
    Use Claude to normalize unusual duration formats to total seconds.

    Handles formats like:
    - "0:00:10" (HH:MM:SS meaning 10 seconds)
    - "6.22" (European style meaning 6 min 22 sec)
    - "5m 57 seconds" (mixed abbreviation and full word)

    Args:
        raw_answer: The raw duration string from student
        api_key: Anthropic API key

    Returns:
        Normalized string (either seconds as number, "DOOR", or "INVALID")
    """
    if not raw_answer or not raw_answer.strip():
        return raw_answer

    if not api_key or not ANTHROPIC_AVAILABLE:
        return raw_answer

    # Skip if it's already a simple format that parse_duration handles well
    raw_clean = raw_answer.strip().lower()

    # Quick check: if it's clearly DOOR/DIAB, don't bother with LLM
    if 'door' in raw_clean or 'diab' in raw_clean:
        return raw_answer

    # Quick check: if it's a simple number, skip LLM
    if re.match(r'^\d+$', raw_clean):
        return raw_answer

    # Quick check: if it matches standard formats we handle well, skip LLM
    # Standard MM:SS format
    if re.match(r'^\d{1,2}:\d{2}$', raw_clean):
        return raw_answer

    # Standard "X minutes Y seconds" format
    if re.match(r'^\d+\s*minutes?\s*\d*\s*seconds?$', raw_clean):
        return raw_answer

    # Use LLM for unusual formats
    try:
        client = Anthropic(api_key=api_key)

        prompt = f"""Convert this duration to total seconds. Return ONLY a number, nothing else.
If it says 'Door', 'DIAB', or similar, return 'DOOR'.
If it's not a valid duration, return 'INVALID'.

Examples:
- "10" → "10"
- "0:00:10" → "10"
- "5m 57 seconds" → "357"
- "6.22" (European for 6:22) → "382"
- "5:30" → "330"
- "2min30" → "150"
- "1:30:00" (HH:MM:SS for 1.5 hours) → "5400"

Input: {raw_answer}"""

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=50,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result = message.content[0].text.strip()

        # Validate the result
        if result == "DOOR":
            return "DOOR"
        elif result == "INVALID":
            return raw_answer  # Let parse_duration handle it
        else:
            # Try to parse as number to validate
            try:
                float(result)
                return result  # Return the seconds as string
            except ValueError:
                return raw_answer  # Invalid response, use original

    except Exception:
        # On any error, fall back to original answer
        return raw_answer

@dataclass
class GradeResult:
    """Result of grading a single question."""
    is_correct: bool
    feedback: str
    calculation: Optional[str] = None  # For showing percentage calculations
    confidence: str = "high"  # "high" or "review" - review means near threshold, needs human check


def parse_duration(duration_str: str) -> Optional[float]:
    """
    Parse a duration string into seconds.
    Handles formats like:
    - "30 seconds", "30 sec", "30s", "30"
    - "2 minutes", "2 min", "2:00", "2'00"
    - "2:45", "2'45", "2 minutes 45 seconds"
    - "5:30", "5 minutes 30 seconds"
    - "DOOR", "Door", "door" -> returns None (special case)
    - French formats: "0,13" (= 0:13 = 13 sec), "2,20" (= 2:20 = 2min 20sec)
    - French formats: "1minutes 20 secondes", "2 minutes 30 secondes"
    """
    if duration_str is None:
        return None

    duration_str = str(duration_str).strip().lower()

    # Check for DIAB/Door
    if 'door' in duration_str or 'diab' in duration_str:
        return None  # Special marker for DIAB

    # Handle French format: "Xminutes Y secondes" or "X minutes Y secondes" (with or without spaces)
    # Must check this BEFORE other processing
    french_full_match = re.match(r'^(\d+)\s*minutes?\s*(\d+)\s*secondes?$', duration_str)
    if french_full_match:
        minutes = int(french_full_match.group(1))
        seconds = int(french_full_match.group(2))
        return minutes * 60 + seconds

    # Handle English format: "X minutes Y seconds" (with or without spaces)
    eng_full_match = re.match(r'^(\d+)\s*minutes?\s*(\d+)\s*seconds?$', duration_str)
    if eng_full_match:
        minutes = int(eng_full_match.group(1))
        seconds = int(eng_full_match.group(2))
        return minutes * 60 + seconds

    # Handle French decimal format: "0,13" or "2,20" -> treat comma as time separator (min:sec)
    # This handles cases like "0,13" meaning 13 seconds, "2,20" meaning 2:20
    french_time_match = re.match(r'^(\d+),(\d{1,2})$', duration_str)
    if french_time_match:
        minutes = int(french_time_match.group(1))
        seconds = int(french_time_match.group(2))
        return minutes * 60 + seconds

    # Handle French shorthand: "3mn2" = 3 min 2 sec, "1m06" = 1 min 6 sec
    shorthand_match = re.match(r'^(\d+)\s*(?:mn|m)\s*(\d+)$', duration_str)
    if shorthand_match:
        minutes = int(shorthand_match.group(1))
        seconds = int(shorthand_match.group(2))
        return minutes * 60 + seconds

    # Check for "X minutes" or "X minute" or "Xm" or "Xmn" without seconds
    # Also handle French: "X minutes" with comma decimal
    mins_only_match = re.match(r'^(\d+(?:[.,]\d+)?)\s*(?:minutes?|mins?|mn|m)$', duration_str)
    if mins_only_match:
        mins_str = mins_only_match.group(1).replace(',', '.')
        return float(mins_str) * 60

    # Check for "X seconds" or "Xs" or "X s" (with or without space)
    secs_only_match = re.match(r'^(\d+(?:[.,]\d+)?)\s*(?:secondes?|seconds?|secs?|s)$', duration_str)
    if secs_only_match:
        secs_str = secs_only_match.group(1).replace(',', '.')
        return float(secs_str)

    # Replace French decimal comma with period for other numeric parsing
    duration_str = duration_str.replace(',', '.')

    # Remove common words (English and French)
    duration_str = duration_str.replace('seconds', '').replace('second', '')
    duration_str = duration_str.replace('secondes', '').replace('seconde', '')
    duration_str = duration_str.replace('minutes', ':').replace('minute', ':')
    duration_str = duration_str.replace('mins', ':').replace('min', ':')
    duration_str = duration_str.replace('sec', '').replace('secs', '')
    duration_str = duration_str.replace('and', '').replace('et', '').strip()

    # Handle formats like 3'20" or 3'20
    duration_str = duration_str.replace("'", ':').replace('"', '')

    # Clean up multiple colons or spaces
    duration_str = re.sub(r'\s+', ' ', duration_str).strip()
    duration_str = re.sub(r':+', ':', duration_str).strip(':')

    try:
        if ':' in duration_str:
            parts = duration_str.split(':')
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) == 2:
                minutes = float(parts[0]) if parts[0] else 0
                seconds = float(parts[1]) if parts[1] else 0
                return minutes * 60 + seconds
            elif len(parts) == 1:
                return float(parts[0])
        else:
            # Just a number - assume seconds if small, could be minutes if context suggests
            value = float(duration_str.split()[0] if ' ' in duration_str else duration_str)
            return value
    except (ValueError, IndexError):
        return None


def format_duration(seconds: float) -> str:
    """Format seconds as a readable duration string."""
    if seconds < 60:
        return f"{int(seconds)} seconds"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if secs == 0:
            return f"{mins} minute{'s' if mins != 1 else ''}"
        else:
            return f"{mins}:{secs:02d}"


def calculate_percentage_increase(old_value: float, new_value: float) -> float:
    """Calculate percentage increase from old to new value."""
    if old_value == 0:
        return 0
    return ((new_value - old_value) / old_value) * 100


def get_guideline_range(duration_seconds: float) -> Tuple[float, float]:
    """
    Get the appropriate percentage increase range based on duration.
    Returns (min_percent, max_percent).
    """
    if duration_seconds < 120:  # Under 2 minutes
        return (10.0, 20.0)
    else:  # Over 2 minutes
        return (5.0, 10.0)


def get_warmup_range(duration_seconds: float) -> Tuple[int, int]:
    """
    Get the appropriate number of warmup steps based on target duration.
    Returns (min_warmups, max_warmups).
    """
    if duration_seconds < 60:  # Under 1 minute
        return (7, 9)
    elif duration_seconds < 300:  # 1 to 5 minutes
        return (4, 7)
    elif duration_seconds < 900:  # 5 to 15 minutes
        return (1, 5)
    else:  # Over 15 minutes
        return (1, 2)


# =============================================================================
# MAISIE GRADING (Questions 1-4)
# =============================================================================

def grade_maisie_q1(answer: str) -> GradeResult:
    """Grade Maisie's Plan 1 target duration. Correct: 20 seconds or less."""
    duration = parse_duration(answer)

    if duration is None:  # DIAB selected
        return GradeResult(
            is_correct=False,
            feedback="Maisie did show signs of anxiety early on, so well done! It is okay to err on the side of caution, especially when just starting out with a dog. However, for Plan 1 Maisie could have started with a target duration exercise rather than Door is a Bore."
        )

    # Borderline zones: near 5 (DIAB threshold), near 10 (conservative threshold), near 20 (pass/fail)
    confidence = "high"
    if 4 <= duration <= 6:  # Near DIAB/target duration boundary
        confidence = "review"
    elif 9 <= duration <= 11:  # Near too-conservative boundary
        confidence = "review"
    elif 19 <= duration <= 22:  # Near pass/fail boundary at 20
        confidence = "review"
    elif 41 <= duration <= 45:  # Near slightly-pushy/too-pushy boundary
        confidence = "review"

    if duration <= 4:
        return GradeResult(
            is_correct=False,
            feedback="Maisie did show signs of anxiety early on, so well done! It is okay to err on the side of caution, especially when just starting out with a dog. However, for anything under 5 seconds we'd start a dog on DIAB and in Maisie's case she does not need to start on DIAB. Maisie was doing well for the first 19 seconds of the video.",
            confidence=confidence
        )
    elif duration <= 9:
        return GradeResult(
            is_correct=False,
            feedback="Maisie was doing well for the first 19 seconds of the video. We start to see her struggle with those repeated yawns and lip licks starting at 20 seconds. It would have been okay to start her around 15 seconds to shave a little time off from those first signs of anxiety. However, it's always okay to err on the side of caution, especially when just starting out with a client.",
            confidence=confidence
        )
    elif duration <= 16:
        return GradeResult(
            is_correct=True,
            feedback="Excellent choice for Maisie's Plan 1. Maisie starts showing anxiety with repeated yawning and lip licking starting at 20 seconds. More signs of anxiety follow throughout the absence. You identified those early signs and set a safe target duration well before they appeared.",
            confidence=confidence
        )
    elif duration <= 19:
        return GradeResult(
            is_correct=True,
            feedback="Nice job catching that Maisie starts showing anxiety with repeated yawning and lip licking starting at 20 seconds. More signs of anxiety follow throughout the absence. Since this is your first time seeing Maisie you could even start closer to 15 seconds just to shave a little time off from where we saw those first signs of anxiety.",
            confidence=confidence
        )
    elif duration == 20:
        return GradeResult(
            is_correct=True,
            feedback="Nice job catching that when Maisie started yawning and lip licking around 20 seconds she was beginning to go over threshold. After that more signs of anxiety followed through the absence. Since her first yawn is 20 seconds into the absence we'd want to start her first exercise slightly before those first signs of anxiety. Starting closer to 15 seconds would be a better choice for Maisie.",
            confidence=confidence
        )
    elif duration <= 43:
        return GradeResult(
            is_correct=False,
            feedback="This target duration is slightly pushy. Maisie does start showing signs of anxiety pretty early on; repeated lip licks and yawns starting at 20 seconds, after which she gets up with a gruff, stretches, and looks at the door stiffly. Then she scratches and stretches. Some of these things could be okay on their own, but we are seeing an escalation of behaviors here. For Maisie, you'd want to set the target duration for Plan 1 to slightly before those very first signs of anxiety.",
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Take another look at the video for Maisie. She starts to show signs of anxiety pretty early on. Watch closely. For Maisie, you'd want to set the target duration for Plan 1 to something you're pretty certain she'll be comfortable doing - a duration that's shorter than where we see those first signs of anxiety. We are looking for less than 20 seconds.",
            confidence=confidence
        )


def grade_maisie_q2(answer: str, q1_answer: str) -> GradeResult:
    """Grade Maisie's Plan 2 target duration. Should be 10-20% increase from Plan 1."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q1_answer)

    if old_duration is None or new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a target duration for this plan."
        )

    if new_duration <= old_duration:
        return GradeResult(
            is_correct=False,
            feedback="This is not correct. Maisie did not need to drop here. Since she aced Plan 1, you should increase the target duration.",
            calculation=f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} (decrease)"
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    min_pct, max_pct = get_guideline_range(old_duration)

    calc_str = f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if within 2% of boundaries
    confidence = "high"
    if abs(increase_pct - min_pct) <= 2:  # Near lower boundary (10%)
        confidence = "review"
    elif abs(increase_pct - max_pct) <= 2:  # Near upper boundary (20%)
        confidence = "review"
    elif 20 < increase_pct <= 23:  # Just over the guideline
        confidence = "review"

    if increase_pct < min_pct:
        return GradeResult(
            is_correct=False,
            feedback=f"Maisie would have been okay to push by the normal guidelines for under 2 minutes of 10-20%. This increase of {increase_pct:.1f}% is a bit conservative.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 0.5:  # Small tolerance
        return GradeResult(
            is_correct=True,
            feedback=f"Well done on selecting a reasonable target increase for Plan 2! This is a {increase_pct:.1f}% increase, which is correctly following the guidelines for increases to target durations under 2 minutes.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= 25:
        return GradeResult(
            is_correct=False,
            feedback=f"You were right to increase the target duration but this increase of {increase_pct:.1f}% is a little over the guidelines for durations under 2 minutes of 10-20%. When just starting out with a dog we'd be more likely to stay within those guidelines.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"The increases here are too high at {increase_pct:.1f}%. Please see the Plan Building Guidelines for target duration increases.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_maisie_q3(answer: str, q2_answer: str) -> GradeResult:
    """Grade Maisie's Plan 3 target duration. Should be 10-20% increase from Plan 2."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q2_answer)

    if old_duration is None or new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a target duration for this plan."
        )

    if new_duration <= old_duration:
        return GradeResult(
            is_correct=False,
            feedback="This is not correct. Maisie did not need to drop here. Since she aced Plan 2, you should increase the target duration.",
            calculation=f"Your Plan 2: {format_duration(old_duration)} -> Plan 3: {format_duration(new_duration)} (decrease)"
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    min_pct, max_pct = get_guideline_range(old_duration)

    calc_str = f"Your Plan 2: {format_duration(old_duration)} -> Plan 3: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if within 2% of boundaries
    confidence = "high"
    if abs(increase_pct - min_pct) <= 2:
        confidence = "review"
    elif abs(increase_pct - max_pct) <= 2:
        confidence = "review"
    elif 20 < increase_pct <= 23:
        confidence = "review"

    if increase_pct < min_pct:
        return GradeResult(
            is_correct=False,
            feedback=f"Maisie would have been okay to push by the normal guidelines for under 2 minutes of 10-20%. This increase of {increase_pct:.1f}% is a bit conservative.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 0.5:
        return GradeResult(
            is_correct=True,
            feedback=f"Well done on selecting another reasonable target increase for Plan 3! This is a {increase_pct:.1f}% increase, which is within the guidelines.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= 25:
        return GradeResult(
            is_correct=False,
            feedback=f"You were right to increase the target duration but this increase of {increase_pct:.1f}% is a little over the guidelines for durations under 2 minutes of 10-20%.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"The increases here are too high at {increase_pct:.1f}%. Please see the Plan Building Guidelines for target duration increases.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_maisie_q4(answer: str) -> GradeResult:
    """Grade Maisie short answer - after 2nd drop, owners can't get out door. Answer: DIAB."""
    answer_lower = answer.lower().strip()

    if 'door' in answer_lower or 'diab' in answer_lower:
        return GradeResult(
            is_correct=True,
            feedback="Good choice of DIAB to get Maisie back to acing sessions, since after the 2nd drop she struggled before the owners could even get out the door."
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Since Maisie has already needed a couple of drops in a row and is now struggling before the owners can get out the door, we'd want to drop to something so easy she almost can't miss. Consider what would be most appropriate here."
        )


# =============================================================================
# MINNA GRADING (Questions 5-8)
# =============================================================================

def grade_minna_q5(answer: str) -> GradeResult:
    """Grade Minna's Plan 1. Correct: DIAB (shows anxiety before owner leaves)."""
    duration = parse_duration(answer)

    if duration is None:  # DIAB selected
        return GradeResult(
            is_correct=True,
            feedback="Spot on selecting DIAB! Minna was showing anxiety before her owner got out the door."
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Minna shows signs of anxiety such as pacing and whining very early on, even before the owner gets out the door. Where would you start a dog who is stressed before the owner even gets out of the door? Be sure to adjust Plans 2 and 3 accordingly."
        )


def grade_minna_q6(answer: str, q5_answer: str) -> GradeResult:
    """Grade Minna's Plan 2. After DIAB, should be 5-6 seconds (or continuing DIAB is acceptable)."""
    duration = parse_duration(answer)
    q5_was_diab = parse_duration(q5_answer) is None

    if duration is None:  # Kept DIAB
        if q5_was_diab:
            return GradeResult(
                is_correct=True,
                feedback="For this assignment, we were assuming Minna completed DIAB in Plan 1 (repeating step 10 up to 5 seconds outside the door). You didn't need to choose DIAB for Plan 2, as that would be overly conservative, but it's acceptable."
            )
        else:
            return GradeResult(
                is_correct=False,
                feedback="Please provide a target duration for Plan 2."
            )

    # If they didn't do DIAB for Q5, this is more complex - use ECF
    if not q5_was_diab:
        q5_duration = parse_duration(q5_answer)
        if q5_duration and duration > 0:
            increase_pct = calculate_percentage_increase(q5_duration, duration)
            # Flag for review if near percentage boundaries
            confidence = "high"
            if abs(increase_pct - 10) <= 2 or abs(increase_pct - 20) <= 2:
                confidence = "review"
            if 10 <= increase_pct <= 20.5:
                return GradeResult(
                    is_correct=True,
                    feedback=f"This is a {increase_pct:.1f}% increase from Plan 1, which follows the guidelines.",
                    calculation=f"Plan 1: {format_duration(q5_duration)} -> Plan 2: {format_duration(duration)}",
                    confidence=confidence
                )

    # Borderline zones for post-DIAB durations
    confidence = "high"
    if 2 <= duration <= 4:  # Near 3 sec boundary
        confidence = "review"
    elif 6 <= duration <= 8:  # Near 6-7 boundary
        confidence = "review"

    # Standard grading for post-DIAB
    if duration < 3:
        return GradeResult(
            is_correct=False,
            feedback="There is some trainer's choice once the dog has been able to do 1 sec in DIAB. Nice job not jumping up too high. We do recommend continuing with DIAB format for anything under 5 seconds. For instance, you'd repeat step 10 building up in 1sec increments to 5sec.",
            confidence=confidence
        )
    elif duration <= 6:
        return GradeResult(
            is_correct=True,
            feedback="Nice progression of increases following DIAB! There is some trainer's choice once the dog has been able to do 1 sec with the owner outside the door in DIAB.",
            confidence=confidence
        )
    elif duration == 7:
        return GradeResult(
            is_correct=False,
            feedback="There is some trainer's choice once the dog has been able to do 1 sec with the owner outside the door in DIAB. The first target duration exercise after DIAB would typically start at 5 sec. If you built up to 5sec in DIAB format, you might get away with 7 sec but we don't want to push our luck.",
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="There is some trainer's choice once the dog has been able to do 1 sec with the owner outside the door in DIAB. You can repeat step 10 building up in 1sec increments to 5sec or try 3sec then switch to a target duration. Either way, this would be too big of a jump for Plan 2.",
            confidence=confidence
        )


def grade_minna_q7(answer: str, q6_answer: str) -> GradeResult:
    """Grade Minna's Plan 3. Should be appropriate increase from Plan 2."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q6_answer)

    # If Q6 was DIAB, then Q7 should be 5-6 seconds
    if old_duration is None:
        # Borderline near 5 sec boundary
        confidence = "high"
        if new_duration and 4 <= new_duration <= 7:
            confidence = "review"

        if new_duration and 5 <= new_duration <= 6:
            return GradeResult(
                is_correct=True,
                feedback="Nice increase from DIAB to Plan 3. For this assignment, we were assuming Minna completed DIAB in Plan 1.",
                confidence=confidence
            )
        elif new_duration and new_duration < 5:
            return GradeResult(
                is_correct=False,
                feedback="We recommend continuing with DIAB format for anything under 5 seconds.",
                confidence=confidence
            )
        else:
            return GradeResult(
                is_correct=False,
                feedback="This is too big of a jump after DIAB.",
                confidence=confidence
            )

    if new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Minna doesn't need DIAB at this point. Please provide a target duration."
        )

    if new_duration <= old_duration:
        return GradeResult(
            is_correct=False,
            feedback="Minna aced Plan 2, so you should increase the target duration for Plan 3."
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    min_pct, max_pct = get_guideline_range(old_duration)

    calc_str = f"Your Plan 2: {format_duration(old_duration)} -> Plan 3: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if near percentage boundaries
    confidence = "high"
    if abs(increase_pct - min_pct) <= 2 or abs(increase_pct - max_pct) <= 2:
        confidence = "review"

    # For very short durations, be more lenient since small absolute changes = big percentages
    if old_duration <= 6:
        # Near 8 sec boundary for short durations
        if 7 <= new_duration <= 9:
            confidence = "review"
        if new_duration <= 8:
            return GradeResult(
                is_correct=True,
                feedback="Nice job selecting an appropriate increase for Plan 3. For such short durations, small absolute increases are appropriate.",
                calculation=calc_str,
                confidence=confidence
            )

    if increase_pct < min_pct - 2:  # Some tolerance for short durations
        return GradeResult(
            is_correct=False,
            feedback=f"This increase of {increase_pct:.1f}% is a bit conservative.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 5:  # More tolerance for short durations
        return GradeResult(
            is_correct=True,
            feedback=f"Nice job selecting an appropriate increase for Plan 3.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"You selected quite a jump from Plan 2 at {increase_pct:.1f}%. This might be more than Minna can cope with.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_minna_q8(answer: str) -> GradeResult:
    """Grade Minna short answer - acing 5 sessions at 10%, what next? Answer: push higher (11-20%)."""
    answer_lower = answer.lower().strip()

    # Check if they gave a duration instead of a percentage
    if 'minute' in answer_lower or ':' in answer_lower:
        # They gave an actual duration - try to figure out the percentage
        # 8 minutes = 480 seconds, 10% would be 528 seconds (8:48)
        return GradeResult(
            is_correct=False,
            feedback="This question is asking what percentage you would increase by, not the actual target duration. Since Minna has been acing session after session, this is a good time to test out pushing a little higher than the guidelines."
        )

    # Try to extract a percentage
    numbers = re.findall(r'(\d+(?:\.\d+)?)\s*%?', answer_lower)

    if numbers:
        pct = float(numbers[0])
        if pct > 10 and pct <= 20:
            return GradeResult(
                is_correct=True,
                feedback="Excellent choice for Minna's next push! Since she is acing session after session this is a good time to test out pushing a little higher than the guidelines."
            )
        elif pct <= 10:
            return GradeResult(
                is_correct=False,
                feedback="Since Minna has been acing session after session, this is a good time to test out pushing a little higher than the guidelines. What might we try instead when a dog is consistently acing sessions?"
            )
        else:
            return GradeResult(
                is_correct=False,
                feedback="Since Minna is acing session after session this is a good time to test out pushing a little higher than the guidelines. Nice job thinking to do that, however, we don't want to risk pushing too high. An increase around 15-20% would be good here."
            )

    # Check for keywords suggesting higher push
    if any(word in answer_lower for word in ['higher', 'more', '15', '20', 'push']):
        return GradeResult(
            is_correct=True,
            feedback="Excellent choice! Since she is acing session after session this is a good time to test out pushing a little higher than the guidelines."
        )

    return GradeResult(
        is_correct=False,
        feedback="Since Minna has been acing session after session, this is a good time to test out pushing a little higher than the guidelines. What might we try instead when a dog is consistently acing sessions?"
    )


# =============================================================================
# OLIVER GRADING (Questions 9-12)
# =============================================================================

def grade_oliver_q9(answer: str) -> GradeResult:
    """Grade Oliver's Plan 1. Correct: 4:00 to 6:09 (video is ~5.5 min, dog does well)."""
    duration = parse_duration(answer)

    if duration is None:  # DIAB selected
        return GradeResult(
            is_correct=False,
            feedback="Oliver did not need to start on Door is a Bore. He did well throughout the video. What would be a good target duration to start him on?"
        )

    # Convert to minutes for easier comparison
    minutes = duration / 60

    # Borderline zones (in minutes): near 4 min, near 6.15 min
    confidence = "high"
    if 3.75 <= minutes <= 4.25:  # Near 4 minute boundary
        confidence = "review"
    elif 5.9 <= minutes <= 6.3:  # Near upper boundary
        confidence = "review"

    if minutes < 1:
        return GradeResult(
            is_correct=False,
            feedback="It's okay for dogs to move around and to walk to the door to watch. This game of going and coming is different, so we will often see this, especially in earlier stages of training even when dogs are not upset. Oliver settled and looked pretty relaxed; He walks toward the door at a normal pace (not frantic), turns his head and moves a bit when he's at the door (so he's not frozen), has alert but soft eyes and soft mouth, and he sits. All that said, Oliver did well here, so what would a good target duration be to start him on?",
            confidence=confidence
        )
    elif minutes < 4:
        return GradeResult(
            is_correct=False,
            feedback="It's okay for dogs to move around and to walk to the door to watch. This game of going and coming is different, so we will often see this, especially in earlier stages of training even when dogs are not upset. Oliver settled and looked pretty relaxed. His Plan 1 target duration could have been closer to the 5-minute range. Take another look at the video.",
            confidence=confidence
        )
    elif minutes < 4.75:
        return GradeResult(
            is_correct=True,
            feedback="It's okay for dogs to move around and to walk to the door to watch. Oliver settled and looked pretty relaxed. His Plan 1 target duration could have been closer to the 5-minute range, but it's best to err on the side of caution!",
            confidence=confidence
        )
    elif minutes <= 5.5:
        return GradeResult(
            is_correct=True,
            feedback="Well done recognizing that Oliver did well for the duration of this exercise! It's okay for dogs to move around and go to the door, as long as there aren't signs of anxiety. You chose an excellent starting duration for Plan 1.",
            confidence=confidence
        )
    elif minutes <= 6.15:
        return GradeResult(
            is_correct=True,
            feedback="Well done recognizing that Oliver did well for the duration of this exercise! It's okay for dogs to move around and go to the door, as long as there aren't signs of anxiety. Since this is an assessment, it was smart that you chose to shave some time off for the first exercise, just in case this happened to be a really good day for Oliver.",
            confidence=confidence
        )
    elif minutes <= 6.25:
        return GradeResult(
            is_correct=False,
            feedback="Well done recognizing that Oliver did well for the duration of this exercise! It's okay for dogs to move around and go to the door, as long as there aren't signs of anxiety. The starting target is a little high though with a push over 10% when just starting with Oliver and if this was an assessment, it would be a good idea to shave some time off for the first exercise instead of push.",
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Well done recognizing that Oliver did well for the duration of this exercise! However, the duration increase from the video is too high and since you are just starting with Oliver, it would be better to shave some time off for the first exercise, just in case this happened to be a really good day for Oliver.",
            confidence=confidence
        )


def grade_oliver_q10(answer: str, q9_answer: str) -> GradeResult:
    """Grade Oliver's Plan 2. Should be 5-10% increase from Plan 1."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q9_answer)

    if old_duration is None or new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a target duration for this plan."
        )

    if new_duration <= old_duration:
        return GradeResult(
            is_correct=False,
            feedback="Oliver did well with Plan 1, so you should increase the target duration for Plan 2.",
            calculation=f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)}"
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    calc_str = f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if within 2% of boundaries (5% or 10%)
    confidence = "high"
    if abs(increase_pct - 5) <= 2:  # Near lower boundary
        confidence = "review"
    elif abs(increase_pct - 10) <= 2:  # Near upper boundary
        confidence = "review"
    elif 10 < increase_pct <= 13:  # Just over the guideline
        confidence = "review"

    # Oliver is over 2 minutes, so 5-10% guideline
    if increase_pct < 4:
        return GradeResult(
            is_correct=False,
            feedback=f"It would have been okay to follow the guidelines here and push by 5-10% for Plan 2. This {increase_pct:.1f}% increase is a bit conservative.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= 10.5:  # Small tolerance
        return GradeResult(
            is_correct=True,
            feedback=f"Excellent progress of duration to Plan 2! This is a {increase_pct:.1f}% increase from Oliver's Plan 1 target duration, which is correctly following the guidelines for increases to target durations over 2 minutes.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= 15:
        return GradeResult(
            is_correct=False,
            feedback=f"The increase from Plan 1 to Plan 2 is a tad higher than the guideline of 5-10% for durations over 2 min at {increase_pct:.1f}%. When just starting out with a dog we'd be more likely to stay within those guidelines.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"The increase to Plan 2 is too high at {increase_pct:.1f}%. Please see the Plan Building Guidelines as a refresher.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_oliver_q11(answer: str, q9_answer: str, q10_answer: str) -> GradeResult:
    """Grade Oliver's Plan 3. Oliver struggled with Plan 2, so should drop back to Plan 1 duration."""
    new_duration = parse_duration(answer)
    q9_duration = parse_duration(q9_answer)
    q10_duration = parse_duration(q10_answer)

    if new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Oliver struggled with Plan 2 but doesn't need DIAB. Please provide a target duration."
        )

    if q10_duration and new_duration >= q10_duration:
        return GradeResult(
            is_correct=False,
            feedback="Oliver struggled with his Plan 2 exercise so we would not want to stick or push. What do we do when a dog struggles?"
        )

    # Should drop back to Q9 answer
    if q9_duration:
        # Borderline: near the 5 second tolerance boundary
        confidence = "high"
        diff = abs(new_duration - q9_duration)
        if 3 <= diff <= 8:  # Near the tolerance boundary
            confidence = "review"

        # Allow some tolerance (within 5 seconds)
        if diff <= 5:
            return GradeResult(
                is_correct=True,
                feedback="Excellent job dropping back to the target duration from the last successful exercise when Oliver struggled! This is the rule of thumb for a first drop.",
                confidence=confidence
            )
        elif new_duration < q9_duration:
            return GradeResult(
                is_correct=False,
                feedback=f"Great job selecting a drop here. But what should we be aiming to drop back to on the first drop? The rule of thumb is to go back to the last successful target duration, which was {format_duration(q9_duration)}.",
                confidence=confidence
            )
        else:
            return GradeResult(
                is_correct=False,
                feedback="This is not correctly following the protocol for a dog's first drop. When a dog struggles, we drop back to the last successful target duration.",
                confidence=confidence
            )

    return GradeResult(
        is_correct=False,
        feedback="Oliver struggled with Plan 2, so we need to drop. The rule of thumb is to drop back to the last successful exercise."
    )


def grade_oliver_q12(answer: str) -> GradeResult:
    """Grade Oliver keys question. Should decrease duration when testing keys."""
    answer_lower = answer.lower().strip()

    if 'decrease' in answer_lower or 'drop' in answer_lower or 'lower' in answer_lower or 'reduce' in answer_lower:
        return GradeResult(
            is_correct=True,
            feedback="Great choice to drop the target duration down when testing out reintroducing the keys. This gives Oliver the best chance of success with this previously triggering cue."
        )
    elif 'key is a bore' in answer_lower or 'kiab' in answer_lower:
        return GradeResult(
            is_correct=False,
            feedback="Before going right to the Key is A Bore, what can we do with the TD to retest the keys since there is a chance that they will no longer be an issue now that we've built up some solid duration?"
        )
    elif 'increase' in answer_lower or 'same' in answer_lower:
        return GradeResult(
            is_correct=False,
            feedback="When testing out adding a previously anxiety-provoking pre-departure cue we'd want to decrease the TD."
        )
    else:
        # Check if they mentioned both decrease and KIAB
        if 'bore' in answer_lower and ('first' in answer_lower or 'try' in answer_lower):
            return GradeResult(
                is_correct=True,
                feedback="Great choice to drop the target duration down when testing out reintroducing the keys."
            )
        return GradeResult(
            is_correct=False,
            feedback="When testing out adding a previously anxiety-provoking pre-departure cue, what would you do with the target duration?"
        )


# =============================================================================
# BELLA GRADING (Questions 13-17)
# =============================================================================

def grade_bella_q13(answer: str) -> GradeResult:
    """Grade Bella's Plan 1. Correct: 2:30 to 3:10 (first whine at 3:10 into absence)."""
    duration = parse_duration(answer)

    if duration is None:  # DIAB selected
        return GradeResult(
            is_correct=False,
            feedback="Bella does not need to start on Door is a Bore. She does well for a good portion of the absence. What would be a good target duration to start her on?"
        )

    minutes = duration / 60

    # Borderline zones: near 2:30 (150 sec), near 3:10 (190 sec)
    confidence = "high"
    if 2.4 <= minutes <= 2.7:  # Near 2:30-2:40 boundary
        confidence = "review"
    elif 3.05 <= minutes <= 3.25:  # Near 3:10 boundary
        confidence = "review"

    if minutes < 1.5:
        return GradeResult(
            is_correct=False,
            feedback="Bella actually does well for a good portion of the absence, she is watching the door and alert, but the rest of her body language is pretty relaxed. She does turn her head at the 1:26 min mark in the video, we will see dogs move around when training which can be normal. Take another peek at the video. Do you see where Bella goes from alert but settled to starting to become anxious? We want to set our first target duration to just before those first signs of anxiety start.",
            confidence=confidence
        )
    elif minutes < 2.5:
        return GradeResult(
            is_correct=False,
            feedback="Bella actually does well for a good portion of the absence. At the 3:14 timestamp, she goes off camera, whines, and comes back. This is followed by escalating signs of anxiety through the remainder of the absence. A target duration just slightly less than 3 minutes would have been a good choice for Bella, but it is always better to err on the side of caution, especially when just starting out with a dog.",
            confidence=confidence
        )
    elif minutes < 2.67:  # 2:40
        return GradeResult(
            is_correct=True,
            feedback="Excellent job spotting where Bella started to get anxious around the 3-minute time stamp. Good call to shave some time off for her first target duration to be safe. The amount we choose to shave off can vary based on different factors.",
            confidence=confidence
        )
    elif minutes <= 3.07:  # Up to 3:04
        return GradeResult(
            is_correct=True,
            feedback="Great starting target for Plan 1 since after Bella quickly trots off and whines more signs of anxiety follow.",
            confidence=confidence
        )
    elif minutes <= 3.15:  # 3:05-3:09
        return GradeResult(
            is_correct=True,
            feedback="Good job noticing that after Bella whines she escalates with more signs of anxiety. You might even want to start closer to 3 minutes or slightly before since after Bella quickly trots off more signs of anxiety follow.",
            confidence=confidence
        )
    elif minutes <= 3.17:  # 3:10
        return GradeResult(
            is_correct=True,
            feedback="Good job noticing that after Bella whines she escalates with more signs of anxiety. Since she whines 3:10 into the absence we'd want to start her first exercise before those first signs of anxiety. Starting closer to 3 minutes or a little before to shave some time off would be a better choice for Bella.",
            confidence=confidence
        )
    elif minutes <= 3.4:  # Up to 3:24
        return GradeResult(
            is_correct=False,
            feedback="Bella started to show first signs of stress before this duration. Remember, we want to go off total absence time, not the time stamp, and the owner left 14 seconds into the video. You'd want to select a target duration for Plan 1 that is slightly shorter than when Bella started to show those first signs of anxiety.",
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Take another look at Bella's video. Do you see or hear any signs of stress, and if so, how long into the absence do they begin? You'd want to select a target duration for Plan 1 that is slightly shorter than that, shaving off some time to play it safe.",
            confidence=confidence
        )


def grade_bella_q13b(answer: str, q13_answer: str) -> GradeResult:
    """Grade Bella's warmups for Plan 1. Should be 4-7 for duration between 1-5 minutes."""
    q13_duration = parse_duration(q13_answer)

    # Try to extract number from answer
    answer_lower = answer.lower().strip()

    if 'none' in answer_lower or answer_lower == '0':
        warmups = 0
    else:
        numbers = re.findall(r'\d+', answer)
        if numbers:
            # Take the first number, or if there's a range like "5-8", take the first
            warmups = int(numbers[0])
        else:
            return GradeResult(
                is_correct=False,
                feedback="Please provide a number of warmup steps."
            )

    # Determine correct range based on their Q13 duration
    if q13_duration:
        min_warmups, max_warmups = get_warmup_range(q13_duration)
    else:
        # Default to 1-5 minute range
        min_warmups, max_warmups = (4, 7)

    if warmups == 0:
        return GradeResult(
            is_correct=False,
            feedback=f"For target durations between 1 and 5 minutes, we should include some warmup steps. What would be an appropriate number of warmups for Bella's duration?"
        )
    elif warmups < min_warmups:
        return GradeResult(
            is_correct=False,
            feedback=f"This number of warmups is a bit low for a target duration in this range. The guidelines suggest {min_warmups}-{max_warmups} warmup steps."
        )
    elif warmups <= max_warmups:
        return GradeResult(
            is_correct=True,
            feedback=f"Good job following the warmup guidelines for a target duration between 1 and 5 minutes."
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"This number of warmups is outside of the guidelines for a target duration between 1 and 5 minutes. The guidelines suggest {min_warmups}-{max_warmups} warmup steps."
        )


def grade_bella_q14(answer: str, q13_answer: str) -> GradeResult:
    """Grade Bella's Plan 2. Bella wobbled on warmups but aced target, so should push 5-10%."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q13_answer)

    if old_duration is None or new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a target duration for this plan."
        )

    if new_duration < old_duration:
        return GradeResult(
            is_correct=False,
            feedback="Even though Bella wobbled on the warmups in Plan 1 she aced the target so you could push ahead with an increase for Plan 2. We base whether to push or drop on how a dog did on the target duration unless they completely fall apart in the warm-ups.",
            calculation=f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} (decrease)"
        )

    if new_duration == old_duration:
        return GradeResult(
            is_correct=False,
            feedback="Since Bella aced the target duration in Plan 1, you should increase for Plan 2.",
            calculation=f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} (same)"
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    min_pct, max_pct = get_guideline_range(old_duration)

    calc_str = f"Your Plan 1: {format_duration(old_duration)} -> Plan 2: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if within 2% of boundaries
    confidence = "high"
    if abs(increase_pct - min_pct) <= 2:
        confidence = "review"
    elif abs(increase_pct - max_pct) <= 2:
        confidence = "review"
    elif max_pct < increase_pct <= max_pct + 3:  # Just over the guideline
        confidence = "review"

    if increase_pct < min_pct - 1:
        return GradeResult(
            is_correct=False,
            feedback=f"This increase of {increase_pct:.1f}% is below the recommended guidelines for increases to target durations {'under' if old_duration < 120 else 'over'} 2 minutes.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 0.5:
        return GradeResult(
            is_correct=True,
            feedback=f"Nice progression of duration to Plan 2! Even though Bella wobbled on the warmups in Plan 1 she aced the target so good call to increase the target for Plan 2.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 3:
        return GradeResult(
            is_correct=False,
            feedback=f"The increase from Plan 1 to Plan 2 at {increase_pct:.1f}% is a tad higher than the guideline of {int(min_pct)}-{int(max_pct)}% for durations {'under' if old_duration < 120 else 'over'} 2 min. When just starting out with a dog we'd be more likely to stay within those guidelines.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"This is a bit too high of an increase from Plan 1 at {increase_pct:.1f}%.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_bella_q14b(answer: str, q13b_answer: str) -> GradeResult:
    """Grade Bella's warmups for Plan 2. Should reduce from Plan 1 since she wobbled."""
    # Extract numbers
    answer_lower = answer.lower().strip()

    if 'none' in answer_lower or answer_lower == '0':
        new_warmups = 0
    else:
        numbers = re.findall(r'\d+', answer)
        new_warmups = int(numbers[0]) if numbers else None

    q13b_lower = q13b_answer.lower().strip() if q13b_answer else ""
    if 'none' in q13b_lower or q13b_lower == '0':
        old_warmups = 0
    else:
        old_numbers = re.findall(r'\d+', q13b_answer) if q13b_answer else []
        old_warmups = int(old_numbers[0]) if old_numbers else 7  # Default assumption

    if new_warmups is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a number of warmup steps."
        )

    if new_warmups == 0:
        return GradeResult(
            is_correct=True,
            feedback="Great job removing the warmups since she struggled. It would also have been fine to test out reducing the number, keeping a few warm up steps."
        )
    elif new_warmups < old_warmups:
        if old_warmups - new_warmups >= 2:
            return GradeResult(
                is_correct=True,
                feedback="Nice job testing out fewer warmups with Bella and keeping them reduced since it helped!"
            )
        else:
            return GradeResult(
                is_correct=True,
                feedback="Great call to reduce warmup steps. It would be best to reduce by a couple steps versus 1, especially since Bella wobbled on a couple."
            )
    else:
        return GradeResult(
            is_correct=False,
            feedback="When a dog seems to get more agitated as the warmups go on what can we test out doing with the warmup steps?"
        )


def grade_bella_q15(answer: str, q14_answer: str) -> GradeResult:
    """Grade Bella's Plan 3. Should be 5-10% or 10-20% increase depending on duration."""
    new_duration = parse_duration(answer)
    old_duration = parse_duration(q14_answer)

    if old_duration is None or new_duration is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a target duration for this plan."
        )

    if new_duration <= old_duration:
        return GradeResult(
            is_correct=False,
            feedback="Bella aced Plan 2, so you should increase the target duration for Plan 3.",
            calculation=f"Your Plan 2: {format_duration(old_duration)} -> Plan 3: {format_duration(new_duration)}"
        )

    increase_pct = calculate_percentage_increase(old_duration, new_duration)
    min_pct, max_pct = get_guideline_range(old_duration)

    calc_str = f"Your Plan 2: {format_duration(old_duration)} -> Plan 3: {format_duration(new_duration)} = {increase_pct:.1f}% increase"

    # Flag for review if within 2% of boundaries
    confidence = "high"
    if abs(increase_pct - min_pct) <= 2:
        confidence = "review"
    elif abs(increase_pct - max_pct) <= 2:
        confidence = "review"
    elif max_pct < increase_pct <= max_pct + 3:  # Just over the guideline
        confidence = "review"

    if increase_pct < min_pct - 1:
        return GradeResult(
            is_correct=False,
            feedback=f"This increase of {increase_pct:.1f}% is below the recommended guidelines for increases to target durations {'under' if old_duration < 120 else 'over'} 2 minutes.",
            calculation=calc_str,
            confidence=confidence
        )
    elif increase_pct <= max_pct + 0.5:
        return GradeResult(
            is_correct=True,
            feedback=f"This is a {increase_pct:.1f}% increase from Bella's Plan 2, which is within the guidelines for durations {'under' if old_duration < 120 else 'over'} 2 min.",
            calculation=calc_str,
            confidence=confidence
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback=f"This is a bit too high of an increase from what you set Bella's Plan 2 target duration at {increase_pct:.1f}%.",
            calculation=calc_str,
            confidence=confidence
        )


def grade_bella_q15b(answer: str, q14b_answer: str) -> GradeResult:
    """Grade Bella's warmups for Plan 3. Should keep reduced or same as Plan 2."""
    answer_lower = answer.lower().strip()

    if 'none' in answer_lower or answer_lower == '0':
        new_warmups = 0
    else:
        numbers = re.findall(r'\d+', answer)
        new_warmups = int(numbers[0]) if numbers else None

    q14b_lower = q14b_answer.lower().strip() if q14b_answer else ""
    if 'none' in q14b_lower or q14b_lower == '0':
        old_warmups = 0
    else:
        old_numbers = re.findall(r'\d+', q14b_answer) if q14b_answer else []
        old_warmups = int(old_numbers[0]) if old_numbers else 0

    if new_warmups is None:
        return GradeResult(
            is_correct=False,
            feedback="Please provide a number of warmup steps."
        )

    if new_warmups <= old_warmups:
        return GradeResult(
            is_correct=True,
            feedback="Good job keeping the warmup steps consistent with Plan 2. This stability in the warmup routine can be beneficial for Bella's progress."
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="Nice job testing out fewer warmups with Bella in Plan 2. Since this helped we would not want to add them back in on later plans."
        )


def grade_bella_q16(answer: str) -> GradeResult:
    """Grade Bella car protocol question. Should use Car is a Bore, not starting with engine on."""
    answer_lower = answer.lower().strip()

    # Check for CIAB/Car is a Bore mention
    has_ciab = 'car is a bore' in answer_lower or 'ciab' in answer_lower or 'bore' in answer_lower

    # Check for intensity reduction
    has_intensity = 'further' in answer_lower or 'distance' in answer_lower or 'away' in answer_lower or 'intensity' in answer_lower

    # Check if they mention starting the engine (bad)
    mentions_starting_engine = ('start' in answer_lower and ('engine' in answer_lower or 'car' in answer_lower)) or 'turn' in answer_lower and 'on' in answer_lower

    # Check for step references
    has_step = 'step' in answer_lower

    if has_ciab and has_step:
        # Check if they're starting on a step before engine
        step_numbers = re.findall(r'step\s*(\d+)', answer_lower)
        if step_numbers:
            step_num = int(step_numbers[0])
            if step_num <= 7:  # Step 7 or before is acceptable (before turning engine on)
                return GradeResult(
                    is_correct=True,
                    feedback="Nice! Since we already know that turning the car on causes anxiety, we can go right to Car is A Bore. Excellent thinking breaking down the process. It's good to start a couple of steps back from where the dog first started showing signs of anxiety. You might try starting with something like step 5 in the driveway."
                )
            else:
                return GradeResult(
                    is_correct=False,
                    feedback="Good thinking to work on Car is a Bore. Since we already know that turning the car on caused anxiety for Bella we would not want to start on a step that has turning the engine on in it. We always want to start on a step that the dog will be completely comfortable with."
                )

    if has_intensity and (has_ciab or 'car' in answer_lower):
        return GradeResult(
            is_correct=True,
            feedback="Nice thinking about parking the car further away to dial down the intensity when it's possible for the owner. If parking further away solves the issue and that is something they want to continue, excellent. It could even be a management tool while working on car is a bore. If the owner will need to have the car closer to home at some point it could work to gradually move the car closer, however, it may be easier to work on Car is a Bore with the car in the driveway/garage if that's the end goal. You might try starting with something like step 5 in the driveway."
        )

    if has_ciab:
        return GradeResult(
            is_correct=True,
            feedback="Good thinking to work on Car is a Bore. You might try starting with something like step 5 in the Car is a Bore plan."
        )

    # Check if they describe CIAB-like steps without using the term
    if ('open' in answer_lower or 'door' in answer_lower or 'sit' in answer_lower or 'get in' in answer_lower) and 'car' in answer_lower:
        if not mentions_starting_engine:
            return GradeResult(
                is_correct=True,
                feedback="Good thinking to work on Car is a Bore. Since we already know that turning the car on caused anxiety for Bella we would not want to start on a step that has turning the engine on in it. We always want to start on a step that the dog will be completely comfortable with."
            )

    if 'assessment' in answer_lower:
        return GradeResult(
            is_correct=False,
            feedback="Since we already know that turning the car on caused anxiety for Bella we would not need to do an assessment. We can go right to the Car is a Bore plan."
        )

    return GradeResult(
        is_correct=False,
        feedback="Since turning the car on caused anxiety for Bella what can we do to help desensitize her to the car?"
    )


def grade_diab_q17(answer: str) -> GradeResult:
    """Grade DIAB warmups question. Should do 1-4 reps of previous steps."""
    answer_lower = answer.lower().strip()

    # Extract numbers
    numbers = re.findall(r'\d+', answer)

    if not numbers:
        if 'one' in answer_lower or 'a rep' in answer_lower or 'couple' in answer_lower:
            return GradeResult(
                is_correct=True,
                feedback="Excellent! We would only need to do a couple repetitions to warmup the dog."
            )
        return GradeResult(
            is_correct=False,
            feedback="Please specify how many repetitions."
        )

    reps = int(numbers[0])

    if reps == 0:
        return GradeResult(
            is_correct=False,
            feedback="You might get away with not doing any warmups for DIAB, especially once the dog becomes a pro at the game. However, when starting it would be good to do 2-3 reps of the previous step or 2 to warm the dog up."
        )
    elif reps <= 3:
        return GradeResult(
            is_correct=True,
            feedback="Excellent! We would only need to do a couple repetitions to warmup the dog."
        )
    elif reps <= 4:
        return GradeResult(
            is_correct=True,
            feedback="You are right that you would not need them to repeat the entire previous step or steps. We'd only need to do a couple of reps to warm up the dog, even 2-3 reps of the previous step or 2 might be enough."
        )
    elif reps <= 10:
        return GradeResult(
            is_correct=False,
            feedback="We'd only need to do a couple of reps to warm up the dog. 2-3 reps of the previous step or 2 is usually good for most dogs."
        )
    else:
        return GradeResult(
            is_correct=False,
            feedback="When doing DIAB we do not need to repeat all 10 reps of the previous steps. That would be too many reps just to complete Step 3. We only need to warm the dog up a little."
        )


# =============================================================================
# MAIN GRADING FUNCTION
# =============================================================================

def grade_submission(answers: dict, api_key: str = None) -> dict:
    """
    Grade a complete submission.

    Args:
        answers: Dictionary with keys like 'q1', 'q2', etc. containing student answers
        api_key: Optional Anthropic API key for LLM-based duration normalization

    Returns:
        Dictionary with grading results for each question
    """
    results = {}

    # Duration questions that need LLM normalization: Q1-3, Q5-7, Q9-11, Q13-15
    duration_questions = ['q1', 'q2', 'q3', 'q5', 'q6', 'q7', 'q9', 'q10', 'q11', 'q13', 'q14', 'q15']

    # Normalize duration answers using LLM if API key is provided
    normalized_answers = answers.copy()
    if api_key:
        for q_id in duration_questions:
            raw_answer = answers.get(q_id, '')
            if raw_answer:
                normalized_answers[q_id] = normalize_duration_with_llm(raw_answer, api_key)

    # Maisie
    results['q1'] = grade_maisie_q1(normalized_answers.get('q1', ''))
    results['q2'] = grade_maisie_q2(normalized_answers.get('q2', ''), normalized_answers.get('q1', ''))
    results['q3'] = grade_maisie_q3(normalized_answers.get('q3', ''), normalized_answers.get('q2', ''))
    results['q4'] = grade_maisie_q4(answers.get('q4', ''))

    # Minna
    results['q5'] = grade_minna_q5(normalized_answers.get('q5', ''))
    results['q6'] = grade_minna_q6(normalized_answers.get('q6', ''), normalized_answers.get('q5', ''))
    results['q7'] = grade_minna_q7(normalized_answers.get('q7', ''), normalized_answers.get('q6', ''))
    results['q8'] = grade_minna_q8(answers.get('q8', ''))

    # Oliver
    results['q9'] = grade_oliver_q9(normalized_answers.get('q9', ''))
    results['q10'] = grade_oliver_q10(normalized_answers.get('q10', ''), normalized_answers.get('q9', ''))
    results['q11'] = grade_oliver_q11(normalized_answers.get('q11', ''), normalized_answers.get('q9', ''), normalized_answers.get('q10', ''))
    results['q12'] = grade_oliver_q12(answers.get('q12', ''))

    # Bella
    results['q13'] = grade_bella_q13(normalized_answers.get('q13', ''))
    results['q13b'] = grade_bella_q13b(answers.get('q13b', ''), normalized_answers.get('q13', ''))
    results['q14'] = grade_bella_q14(normalized_answers.get('q14', ''), normalized_answers.get('q13', ''))
    results['q14b'] = grade_bella_q14b(answers.get('q14b', ''), answers.get('q13b', ''))
    results['q15'] = grade_bella_q15(normalized_answers.get('q15', ''), normalized_answers.get('q14', ''))
    results['q15b'] = grade_bella_q15b(answers.get('q15b', ''), answers.get('q14b', ''))
    results['q16'] = grade_bella_q16(answers.get('q16', ''))

    # DIAB
    results['q17'] = grade_diab_q17(answers.get('q17', ''))

    return results


def determine_overall_grade(results: dict) -> Tuple[str, list]:
    """
    Determine if submission should be CLEARED or RESUBMIT.

    Returns:
        Tuple of (grade, list of questions to resubmit)
    """
    incorrect_questions = []

    question_labels = {
        'q1': "Maisie's Plan 1 Target Duration",
        'q2': "Maisie's Plan 2 Target Duration",
        'q3': "Maisie's Plan 3 Target Duration",
        'q4': "Maisie After Struggle",
        'q5': "Minna's Plan 1 Target Duration",
        'q6': "Minna's Plan 2 Target Duration",
        'q7': "Minna's Plan 3 Target Duration",
        'q8': "Minna Target Duration Increase",
        'q9': "Oliver's Plan 1 Target Duration",
        'q10': "Oliver's Plan 2 Target Duration",
        'q11': "Oliver's Plan 3 Target Duration",
        'q12': "Oliver Keys Testing",
        'q13': "Bella's Plan 1 Target Duration",
        'q13b': "Bella's Plan 1 Warmups",
        'q14': "Bella's Plan 2 Target Duration",
        'q14b': "Bella's Plan 2 Warmups",
        'q15': "Bella's Plan 3 Target Duration",
        'q15b': "Bella's Plan 3 Warmups",
        'q16': "Bella Car Protocol",
        'q17': "DIAB Warmups"
    }

    for q_id, result in results.items():
        if not result.is_correct:
            incorrect_questions.append((q_id, question_labels.get(q_id, q_id)))

    # Determine if resubmit needed
    # Resubmit if: multiple pushy errors, confusion about DIAB, or pattern of issues
    if len(incorrect_questions) == 0:
        return "Cleared", []
    elif len(incorrect_questions) <= 2:
        # Could be cleared with feedback, or resubmit for key errors
        # Check if errors are on critical questions
        critical_errors = [q for q, _ in incorrect_questions if q in ['q1', 'q5', 'q9', 'q13', 'q4']]
        if critical_errors:
            return "Resubmit", incorrect_questions
        else:
            return "Cleared", incorrect_questions
    else:
        return "Resubmit", incorrect_questions
