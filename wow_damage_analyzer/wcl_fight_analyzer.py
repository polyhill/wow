import requests
import pandas as pd
import logging
import math
import random
import os
from decimal import Decimal, getcontext, ROUND_CEILING, ROUND_HALF_EVEN

getcontext().prec = 10

# --- Configuration ---
# It is recommended to load the API key from a secure configuration file or environment variable.
try:
    from .config import WCL_API_KEY
except ImportError:
    WCL_API_KEY = os.environ.get("WCL_API_KEY")

if not WCL_API_KEY:
    raise ValueError("WCL_API_KEY not found. Please set it in config.py or as an environment variable.")

WCL_V1_API_URL = "https://www.warcraftlogs.com:443/v1"  # Base URL for the WCL API v1.

# --- Constants ---

# Hit Type Constants from WCL, used to identify the outcome of a combat event.
HIT_TYPE_MISS = 0
HIT_TYPE_HIT = 1
HIT_TYPE_CRIT = 2
HIT_TYPE_BLOCK = 4
HIT_TYPE_GLANCE = 6
HIT_TYPE_DODGE = 7
HIT_TYPE_PARRY = 8
HIT_TYPE_IMMUNE = 10
HIT_TYPE_RESIST = 14
HIT_TYPE_PARTIAL_RESIST = 16

# Damage multipliers for critical strikes.
CRIT_MULTIPLIER_ABILITIES = Decimal('2.2')  # For abilities, assuming relevant talents.
CRIT_MULTIPLIER_MELEE = Decimal('2.0')      # For standard melee attacks.

# Damage multiplier for the Death Wish warrior ability.
DEATH_WISH_MULTIPLIER = Decimal('1.2')

# Whitelist for multi-target boss fights to ensure only relevant targets are included in the analysis.
# This is necessary for fights where a boss consists of multiple entities.
WHITELISTED_TARGETS = {
    "克苏恩": ["克苏恩", "克苏恩之眼"],  # C'Thun and Eye of C'Thun
    "安其拉三宝": ["维姆", "亚尔基公主", "克里勋爵"],  # The Bug Trio: Vem, Princess Yauj, Lord Kri
}

# --- Cache ---
# A simple in-memory cache to store report details and avoid redundant API calls for the same report.
_report_details_cache = {}

# --- Core API Functions ---

def get_report_details(report_code):
    """
    Fetches the full details of a report from the WCL API.
    Uses a cache to avoid redundant API calls for the same report code.

    :param report_code: The unique code for the WCL report.
    :return: A dictionary containing the report details, or None if an error occurs.
    """
    if report_code in _report_details_cache:
        return _report_details_cache[report_code]

    fights_url = f"{WCL_V1_API_URL}/report/fights/{report_code}"
    params = {"api_key": WCL_API_KEY}
    try:
        response = requests.get(fights_url, params=params)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        details = response.json()
        _report_details_cache[report_code] = details  # Cache the successful response
        return details
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching report details from WCL API v1: {e}")
        return None

def get_fight_events(report_code, start_time, end_time, character_id):
    """
    Fetches all combat events for a specific character within a given time range for a fight.

    :param report_code: The WCL report code.
    :param start_time: The start timestamp of the fight in milliseconds.
    :param end_time: The end timestamp of the fight in milliseconds.
    :param character_id: The ID of the character to fetch events for.
    :return: A list of combat events, or None if an error occurs.
    """
    events_url = f"{WCL_V1_API_URL}/report/events/{report_code}"
    params = {
        "api_key": WCL_API_KEY,
        "start": start_time,
        "end": end_time,
        "sourceid": character_id,
        "translate": "true"  # Request translated event data
    }
    try:
        response = requests.get(events_url, params=params)
        response.raise_for_status()
        data = response.json()
        return data.get('events', [])
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching events from WCL API v1: {e}")
        return None

# --- Data Extraction Functions ---

def get_fight_data(report_code, boss_only=False):
    """
    Extracts a simplified list of fights from the report details.

    :param report_code: The WCL report code.
    :param boss_only: If True, filters for successful boss fights only.
    :return: A list of dictionaries, each representing a fight with its ID and name.
    """
    details = get_report_details(report_code)
    if not details or 'fights' not in details:
        return []
    
    fights = details['fights']
    if boss_only:
        # Filter for boss fights that were successful kills.
        fights = [f for f in fights if f.get('boss') != 0 and f.get('kill') == True]
        
    return [{'id': f['id'], 'name': f['name'], 'duration': f['end_time'] - f['start_time']} for f in fights]

def get_warrior_players(report_code):
    """
    Extracts a list of warrior players from the report details.

    :param report_code: The WCL report code.
    :return: A list of dictionaries, each representing a warrior player with their ID and name.
    """
    details = get_report_details(report_code)
    if not details or 'friendlies' not in details:
        return []
    
    # Filters for players of the 'Warrior' class, excluding pets.
    warriors = [
        p for p in details['friendlies'] 
        if p.get('type') == 'Warrior' and p.get('name') != 'Pet'
    ]
    return [{'id': p['id'], 'name': p['name']} for p in warriors]

def get_character_faction(details):
    """
    Determines the character's faction by checking for the presence of Paladins (Alliance-exclusive).
    
    :param details: The report details dictionary.
    :return: 'Alliance', 'Horde', or 'Unknown'.
    """
    if not details or 'friendlies' not in details:
        return "Unknown"

    # If a Paladin is found in the raid, the faction is Alliance.
    is_alliance = next((True for p in details['friendlies'] if p['type'] == 'Paladin'), False)

    if is_alliance:
        return "Alliance"
    else:
        # This is a simplification; a more robust check might be needed for mixed-faction scenarios.
        return "Horde"

def get_boss_list(details, fight_id):
    """
    Extracts a list of boss NPCs involved in a specific fight.

    :param details: The report details dictionary.
    :param fight_id: The ID of the fight to analyze.
    :return: A list of dictionaries, each representing a boss with its ID, GUID, and name.
    """
    bosses = {}  # Use a dict to ensure each boss is listed only once per fight.

    for enemy in details.get('enemies', []):
        if enemy.get('type') == 'Boss':
            for f in enemy.get('fights', []):
                if f.get('id') == fight_id:
                    bosses[enemy.get('id')] = {
                        'id': enemy.get('id'),
                        'guid': enemy.get('guid'),
                        'name': enemy.get('name')
                    }
                    break

    return list(bosses.values())

def analyze_buffs_and_debuffs(events, fight_duration, character_id):
    """
    Analyzes buff and debuff events to calculate uptime and identify static multipliers.

    :param events: A list of combat events.
    :param fight_duration: The total duration of the fight in seconds.
    :param character_id: The ID of the character being analyzed.
    :return: A dictionary of buff and debuff multipliers and uptime windows.
    """
    multipliers = {
        'sayges_dark_fortune': Decimal('1.0'),
        'spirit_of_zandalar': Decimal('1.0'),
        'death_wish_uptime': [],
        'recklessness_uptime': []
    }
    
    # Check for static world buffs in the auras of the first event.
    if events and 'auras' in events[0]:
        for aura in events[0]['auras']:
            if aura.get('ability') == 23768:  # Sayge's Dark Fortune of Damage
                multipliers['sayges_dark_fortune'] = Decimal('1.1')
            elif aura.get('ability') == 355365:  # Spirit of Zandalar
                multipliers['spirit_of_zandalar'] = Decimal('1.15')

    # Track uptime for dynamic buffs like Death Wish and Recklessness.
    death_wish_start_time = None
    recklessness_start_time = None
    for event in events:
        ability = event.get('ability', {})
        # Death Wish (Ability ID 12328)
        if ability.get('guid') == 12328 and event.get('targetID') == character_id:
            if event.get('type') == 'applydebuff':
                death_wish_start_time = event.get('timestamp')
            elif event.get('type') == 'removedebuff' and death_wish_start_time is not None:
                multipliers['death_wish_uptime'].append((death_wish_start_time, event.get('timestamp')))
                death_wish_start_time = None
        # Recklessness (Ability ID 1719)
        elif ability.get('guid') == 1719 and event.get('targetID') == character_id:
            if event.get('type') == 'applybuff':
                recklessness_start_time = event.get('timestamp')
            elif event.get('type') == 'removebuff' and recklessness_start_time is not None:
                multipliers['recklessness_uptime'].append((recklessness_start_time, event.get('timestamp')))
                recklessness_start_time = None
    
    # If buffs are still active at the end of the fight, cap their duration.
    if death_wish_start_time is not None:
        multipliers['death_wish_uptime'].append((death_wish_start_time, fight_duration * Decimal(1000)))
    if recklessness_start_time is not None:
        multipliers['recklessness_uptime'].append((recklessness_start_time, fight_duration * Decimal(1000)))
    
    return multipliers

def classify_swings(events, mh_speed, oh_speed):
    """
    Classifies Melee, Heroic Strike, and Cleave events as main-hand or off-hand.
    This is a heuristic that assumes main-hand swings generally do more damage.
    It sorts swings by damage and assigns the top portion to the main hand
    based on the ratio of weapon speeds.

    :param events: A list of combat events.
    :param mh_speed: The speed of the main-hand weapon.
    :param oh_speed: The speed of the off-hand weapon.
    :return: The list of events with an added 'hand' key ('main' or 'off') for relevant swings.
    """
    swing_events = [e for e in events if e.get('ability', {}).get('name') in ['Melee', 'Heroic Strike', 'Cleave']]
    melee_events = [e for e in swing_events if e.get('ability', {}).get('name') == 'Melee']
    
    # Separate melee events by hit type for more accurate classification.
    hit_crit_melee_events = [e for e in melee_events if e.get('hitType') in [HIT_TYPE_HIT, HIT_TYPE_CRIT]]
    glance_melee_events = [e for e in melee_events if e.get('hitType') == HIT_TYPE_GLANCE]
    miss_melee_events = [e for e in melee_events if e.get('hitType') in [HIT_TYPE_MISS, HIT_TYPE_DODGE, HIT_TYPE_PARRY, HIT_TYPE_BLOCK]]
    
    if not swing_events:
        return events

    mh_speed = Decimal(mh_speed)
    oh_speed = Decimal(oh_speed)

    # Calculate the expected proportion of main-hand attacks based on weapon speeds.
    if mh_speed == Decimal(0) or oh_speed == Decimal(0):
        mh_proportion = Decimal('0.5')
    else:
        total_inverse_speed = (Decimal('1') / mh_speed) + (Decimal('1') / oh_speed)
        mh_proportion = (Decimal('1') / mh_speed) / total_inverse_speed
    
    # Adjust proportion for non-melee swings (HS, Cleave) which are always main-hand.
    if len(melee_events) > 0:
        mh_real_proportion = max(Decimal(0), (Decimal(len(swing_events)) * mh_proportion).to_integral_value(rounding=ROUND_CEILING) - (len(swing_events) - len(melee_events))) / Decimal(len(melee_events))
    else:
        mh_real_proportion = Decimal(0)

    # Sort damaging events to assume higher damage comes from the main hand.
    hit_crit_melee_events.sort(key=lambda e: e.get('amount', 0), reverse=True)
    glance_melee_events.sort(key=lambda e: e.get('amount', 0), reverse=True)

    num_mh_hit = (Decimal(len(hit_crit_melee_events)) * mh_real_proportion).to_integral_value(rounding=ROUND_CEILING)
    num_mh_glance = (Decimal(len(glance_melee_events)) * mh_real_proportion).to_integral_value(rounding=ROUND_CEILING)

    # Classify hit and crit events.
    for i, event in enumerate(hit_crit_melee_events):
        event['hand'] = 'main' if i < num_mh_hit else 'off'

    # Classify glancing blows.
    for i, event in enumerate(glance_melee_events):
        event['hand'] = 'main' if i < num_mh_glance else 'off'

    # Deterministically classify misses based on the expected proportion to ensure consistent results.
    num_misses = len(miss_melee_events)
    if num_misses > 0:
        num_mh_to_assign = (Decimal(num_misses) * mh_real_proportion).quantize(Decimal('1'), rounding=ROUND_HALF_EVEN)
        num_oh_to_assign = num_misses - num_mh_to_assign
        
        current_mh = 0
        current_oh = 0

        for event in miss_melee_events:
            # Use a ratio-based approach to decide which hand to assign.
            # This ensures an even, deterministic distribution of main-hand and off-hand misses
            # that matches the overall expected proportion.
            assign_main = False
            # Handle cases where one hand has 0 misses to avoid division by zero.
            if num_oh_to_assign == 0:
                assign_main = True
            elif num_mh_to_assign == 0:
                assign_main = False
            # Assign to the hand that is "behind" in its assignment ratio.
            elif (Decimal(current_mh) / num_mh_to_assign) <= (Decimal(current_oh) / num_oh_to_assign):
                assign_main = True

            if assign_main and current_mh < num_mh_to_assign:
                event['hand'] = 'main'
                current_mh += 1
            elif current_oh < num_oh_to_assign:
                event['hand'] = 'off'
                current_oh += 1
            else:
                # This is a fallback, should not be strictly necessary with correct logic but ensures all events are assigned.
                event['hand'] = 'main'
                current_mh += 1
            
    return events

def _get_damage_multipier(base_damage_multiplier, death_wish_uptime, event):
    """Calculates the damage multiplier for a single event based on active buffs."""
    timestamp = event.get('timestamp', 0)
    damage_gain = base_damage_multiplier
    for start, end in death_wish_uptime:
        if start <= timestamp <= end:
            damage_gain *= DEATH_WISH_MULTIPLIER
            break
    return damage_gain

def _get_crit_multipier(key):
    """Returns the appropriate crit multiplier for an ability or melee swing."""
    return CRIT_MULTIPLIER_MELEE if key in ["main", "off"] else CRIT_MULTIPLIER_ABILITIES

def get_ability_stats(events, buff_multipliers):
    """
    Calculates detailed statistics for each ability, including hit, crit, miss rates, and average damage.
    This data is crucial for the simulation part of the damage calculation.

    :param events: A list of combat events.
    :param buff_multipliers: A dictionary of active buff multipliers.
    :return: A dictionary of statistics for each ability.
    """
    # Initialize statistics dictionary for all relevant abilities.
    ability_keys = ['main', 'off', 'Heroic Strike', 'Cleave', 'Execute', 'Bloodthirst', 'Whirlwind']
    stats = {key: {'_total_hit_damage': Decimal(0), 'avg_hit_damage': Decimal(0), 'attacks': 0, 'hit': 0, 'crit': 0, 'glance': 0, 'dodge': 0, 'parry': 0, 'miss': 0, 'block': 0, 'unknown': 0} for key in ability_keys}

    base_damage_multiplier = buff_multipliers.get('sayges_dark_fortune', Decimal('1.0'))
    death_wish_uptime = buff_multipliers.get('death_wish_uptime', [])

    for event in events:
        ability_name = event.get('ability', {}).get('name')
        hand = event.get('hand')
        key = hand if hand else ability_name
            
        if key in stats:
            stat_block = stats[key]
            stat_block['attacks'] += 1
            event_damage = Decimal(event.get('amount', 0))
            hit_damage = event_damage
            hit_type = event.get('hitType')
            
            # Calculate the damage multiplier for this specific event.
            event['damage_multiplier'] = _get_damage_multipier(base_damage_multiplier, death_wish_uptime, event)
            
            # Categorize the event outcome and normalize damage for hits and crits.
            if hit_type == HIT_TYPE_HIT: 
                stat_block['hit'] += 1
                hit_damage = event_damage / event['damage_multiplier']
            elif hit_type == HIT_TYPE_CRIT: 
                stat_block['crit'] += 1
                hit_damage = event_damage / event['damage_multiplier'] / _get_crit_multipier(key)
            elif hit_type == HIT_TYPE_GLANCE: stat_block['glance'] += 1
            elif hit_type == HIT_TYPE_DODGE: stat_block['dodge'] += 1
            elif hit_type == HIT_TYPE_PARRY: stat_block['parry'] += 1
            elif hit_type == HIT_TYPE_MISS: stat_block['miss'] += 1
            elif hit_type == HIT_TYPE_BLOCK: stat_block['block'] += 1
            else: 
                stat_block['unknown'] += 1

            stat_block['_total_hit_damage'] += hit_damage
    
    # Calculate the average non-crit, non-glancing hit damage for each ability.
    for key in stats:
        stat_block = stats[key]
        num_damaging_hits = stat_block['hit'] + stat_block['crit'] + stat_block['glance']
        stat_block['avg_hit_damage'] = stat_block['_total_hit_damage'] / max(Decimal(1), Decimal(num_damaging_hits))
    
    return stats

# --- Analysis Functions ---

def process_damage_events(events, character_id, target_id_to_name, whitelisted_targets=None):
    """
    Filters raw event data to include only relevant damage events dealt by the specified character.

    :param events: A list of all combat events.
    :param character_id: The ID of the character to filter for.
    :param target_id_to_name: A mapping of target IDs to their names.
    :param whitelisted_targets: A list of target names to include for specific fights.
    :return: A list of filtered damage events.
    """
    if not events:
        return []

    attack_events = []
    for event in events:
        # Filter for damage events from the specified character to a non-friendly target.
        if (event.get('type') == 'damage' and 
            event.get('sourceID') == character_id and 
            not event.get('targetIsFriendly')):
            
            target_name = target_id_to_name.get(event.get('targetID'))
            # If a whitelist is provided, only include events targeting whitelisted enemies.
            if whitelisted_targets:
                if target_name in whitelisted_targets:
                    attack_events.append(event)
            else:
                attack_events.append(event)
    return attack_events

def analyze_damage_summary(attack_events, fight_duration_seconds):
    """
    Analyzes a list of attack events and returns a pandas DataFrame summarizing the damage.

    :param attack_events: A list of filtered damage events.
    :param fight_duration_seconds: The total duration of the fight in seconds.
    :return: A pandas DataFrame with a detailed damage summary.
    """
    if not attack_events:
        return pd.DataFrame()

    df = pd.DataFrame(attack_events)
    df['damage'] = df['amount'].apply(lambda x: Decimal(x) if pd.notnull(x) else Decimal(0))
    df['ability'] = df['ability'].apply(lambda x: x.get('name', 'Unknown'))
    
    # Create boolean columns for each hit type to facilitate aggregation.
    df['is_miss'] = df['hitType'] == HIT_TYPE_MISS
    df['is_hit'] = df['hitType'] == HIT_TYPE_HIT
    df['is_crit'] = df['hitType'] == HIT_TYPE_CRIT
    df['is_block'] = df['hitType'] == HIT_TYPE_BLOCK
    df['is_glance'] = df['hitType'] == HIT_TYPE_GLANCE
    df['is_dodge'] = df['hitType'] == HIT_TYPE_DODGE
    df['is_parry'] = df['hitType'] == HIT_TYPE_PARRY
    df['is_immune'] = df['hitType'] == HIT_TYPE_IMMUNE
    df['is_resist'] = df['hitType'] == HIT_TYPE_RESIST
    df['is_partial_resist'] = df['hitType'] == HIT_TYPE_PARTIAL_RESIST

    # Group by ability and aggregate statistics.
    summary = df.groupby("ability").agg(
        total_damage=("damage", "sum"),
        casts=("timestamp", "count"),
        hits=("is_hit", "sum"),
        crits=("is_crit", "sum"),
        misses=("is_miss", "sum"),
        dodges=("is_dodge", "sum"),
        parries=("is_parry", "sum"),
        glances=("is_glance", "sum"),
        blocks=("is_block", "sum"),
        immune=("is_immune", "sum"),
        resist=("is_resist", "sum"),
        partial_resist=("is_partial_resist", "sum"),
    ).reset_index()

    # Calculate derived statistics like crit rate and miss rate.
    summary['actual_hits'] = summary['hits'] + summary['crits'] + summary['glances'] + summary['blocks']
    summary['crit_rate'] = summary.apply(lambda row: (Decimal(str(row['crits'])) / (Decimal(str(row['actual_hits'])) if row['actual_hits'] > 0 else Decimal(1))) * Decimal(100), axis=1)
    summary['total_misses'] = summary['misses'] + summary['dodges'] + summary['parries'] + summary['resist']
    summary['miss_rate'] = summary.apply(lambda row: (Decimal(str(row['total_misses'])) / (Decimal(str(row['casts'])) if row['casts'] > 0 else Decimal(1))) * Decimal(100), axis=1)

    # Consolidate 'hits' to include all damaging outcomes for display purposes.
    summary['hits'] = summary['actual_hits']
    summary = summary.drop(columns=['actual_hits'])

    # Calculate damage percentage relative to the total damage dealt.
    total_damage_dealt = summary['total_damage'].sum()
    summary['damage_percent'] = summary.apply(lambda row: (row['total_damage'] / total_damage_dealt) * Decimal(100) if total_damage_dealt > 0 else Decimal(0), axis=1)

    # Calculate DPS.
    summary['dps'] = summary.apply(lambda row: row['total_damage'] / fight_duration_seconds if fight_duration_seconds > 0 else Decimal(0), axis=1)
        
    # Sort the summary by total damage in descending order.
    summary = summary.sort_values(by='total_damage', ascending=False)

    # Add a 'Total' row to the summary DataFrame.
    total_dps = summary['total_damage'].sum() / fight_duration_seconds if fight_duration_seconds > 0 else Decimal(0)
    total_row = pd.DataFrame({
        'ability': ['Total'],
        'total_damage': [summary['total_damage'].sum()],
        'dps': [total_dps],
        'damage_percent': [Decimal(100)],
        'casts': [summary['casts'].sum()],
        'hits': [summary['hits'].sum()],
        'crits': [summary['crits'].sum()],
        'misses': [summary['misses'].sum()],
        'dodges': [summary['dodges'].sum()],
        'parries': [summary['parries'].sum()],
        'crit_rate': [(Decimal(str(summary['crits'].sum())) / (Decimal(str(summary['hits'].sum())) + Decimal(str(summary['crits'].sum())))) * Decimal(100) if (summary['hits'].sum() + summary['crits'].sum()) > 0 else Decimal(0)],
        'miss_rate': [(Decimal(str(summary['total_misses'].sum())) / Decimal(str(summary['casts'].sum()))) * Decimal(100) if summary['casts'].sum() > 0 else Decimal(0)]
    })
    
    summary = pd.concat([summary, total_row], ignore_index=True)
    
    # Replace NaN with 0 to ensure the output is valid JSON.
    summary.fillna(0, inplace=True)
    
    return summary

def run_full_analysis(report_code, fight_id, character_id, current_status):
    """
    Orchestrates the full analysis pipeline for a given fight and player.
    Fetches report details, events, classifies swings, analyzes buffs, and generates a damage summary.

    :param report_code: The WCL report code.
    :param fight_id: The ID of the fight to analyze.
    :param character_id: The ID of the character to analyze.
    :param current_status: A dictionary of the character's current stats (e.g., weapon speeds).
    :return: A dictionary containing the complete analysis results.
    """
    details = get_report_details(report_code)
    if not details:
        raise ValueError("Could not fetch report details.")
        
    target_fight = next((f for f in details.get('fights', []) if f['id'] == fight_id), None)
    if not target_fight:
        raise ValueError(f"Fight with ID {fight_id} not found.")

    start_time = target_fight['start_time']
    end_time = target_fight['end_time']
    fight_duration = Decimal(end_time - start_time) / Decimal(1000)

    events = get_fight_events(report_code, start_time, end_time, character_id)
    if not events:
        # Return an empty structure if no events are found.
        return {
            'damage_summary': pd.DataFrame(),
            'events': [],
            'fight_duration': 0,
            'buff_multipliers': {},
            'ability_stats': {},
            'boss_list': [],
            'character_faction': ''
        }

    # --- Main Analysis Steps ---
    
    # 1. Analyze buffs and debuffs to get multipliers and uptimes.
    buff_multipliers = analyze_buffs_and_debuffs(events, fight_duration, character_id)
    
    # 2. Process and filter damage events.
    target_id_to_name = {enemy['id']: enemy['name'] for enemy in details.get('enemies', [])}
    whitelisted = WHITELISTED_TARGETS.get(target_fight['name'])    
    damage_events = process_damage_events(events, character_id, target_id_to_name, whitelisted_targets=whitelisted)    
    
    # 3. Generate a preliminary damage summary.
    damage_summary_df = analyze_damage_summary(damage_events, fight_duration)

    # 4. Classify melee swings into main-hand and off-hand.
    damage_events = classify_swings(damage_events, current_status.get('main_hand_speed', '2.4'), current_status.get('off_hand_speed', '1.8'))
    
    # 5. Calculate detailed ability statistics for simulation.
    ability_stats = get_ability_stats(damage_events, buff_multipliers)
    
    # 6. Determine character faction and get the list of bosses.
    character_faction = get_character_faction(details)
    boss_list = get_boss_list(details, fight_id)
    
    logging.info(f"--- Full Analysis for {target_fight.get('name')}({character_faction}) of report uri('{report_code}') ---")
    logging.info(f"Buff mult: {buff_multipliers}")
    logging.info(f"Main Hand: {ability_stats.get('main', {})}")
    logging.info(f"Off Hand : {ability_stats.get('off', {})}")
    logging.info("--------------------------")
    
    return {
        'damage_summary': damage_summary_df,
        'events': damage_events,
        'fight_duration': fight_duration,
        'buff_multipliers': buff_multipliers,
        'ability_stats': ability_stats,
        'boss_list': boss_list,
        'character_faction': character_faction
    }
