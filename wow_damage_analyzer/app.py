import logging
import yaml
from flask import Flask, render_template, request, jsonify
import pandas as pd
from wcl_fight_analyzer import get_fight_data, get_warrior_players, run_full_analysis, get_report_details, get_boss_list
from attack_table_damage import AttackTableDamageCalculator

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

EMPTY_ATTRIBUTES = {
    "strength": 0,
    "agility": 0,
    "attackPower": 0,
    "crit": 0,
    "hit": 0,
    "mainHandSkill": 0,
    "offHandSkill": 0
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/fights/<report_id>')
def api_get_fights(report_id):
    try:
        fights = get_fight_data(report_id, boss_only=True)
        return jsonify(fights)
    except Exception as e:
        app.logger.error(f"Error fetching fights for report {report_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/players/<report_id>')
def api_get_players(report_id):
    try:
        players = get_warrior_players(report_id)
        return jsonify(players)
    except Exception as e:
        app.logger.error(f"Error fetching players for report {report_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/report/<report_id>')
def api_get_report_metadata(report_id):
    try:
        details = get_report_details(report_id)
        if not details:
            return jsonify({'error': 'Report not found'}), 404
        
        import datetime
        start_time = datetime.datetime.fromtimestamp(details.get('start', 0) / 1000).strftime('%Y-%m-%d %H:%M')
        
        return jsonify({
            'title': details.get('title'),
            'startTime': start_time
        })
    except Exception as e:
        app.logger.error(f"Error fetching report metadata for {report_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/analyze', methods=['POST'])
def analyze():
    data = request.json
    report_id = data.get('report_id')
    fight_id = int(data.get('fight_id'))
    player_id = int(data.get('player_id'))
    current_status = data.get('current_status', {})
    attributes = data.get('attributes', {})

    try:
        # Get the damage breakdown from the actual WCL data
        analysis_result = run_full_analysis(report_id, fight_id, player_id, current_status)
        damage_summary_df = analysis_result['damage_summary']
        events = analysis_result['events']
        fight_duration = analysis_result['fight_duration']
        buff_multipliers = analysis_result['buff_multipliers']
        ability_stats = analysis_result['ability_stats']
        boss_list = analysis_result['boss_list']
        character_faction = analysis_result['character_faction']
        
        # Extract base stats from the summary for the new calculator
        total_row = damage_summary_df[damage_summary_df['ability'] == 'Total'].iloc[0]
        base_stats = {
            'crit': total_row.get('crit_rate', 0),
            'miss': total_row.get('miss_rate', 0)
        }

        # Initialize calculators
        damage_calculator = AttackTableDamageCalculator(
            boss_list=boss_list,
            events=events,
            fight_duration=fight_duration,
            buff_multipliers=buff_multipliers,
            ability_stats=ability_stats,
            current_status=current_status,
            attributes=attributes,
            character_faction=character_faction
        )
        
        # Perform calculations
        # Calculate AP DPS gain details
        ap_details_by_ability = {}
        # Calculate AP DPS curve
        ap_dps_curve = []
        ap_attributes = EMPTY_ATTRIBUTES.copy()
        for i in range(0, 201, 10):  # Simulate for 0 to 500 AP
            ap_attributes['attackPower'] = i
            dps_gain = damage_calculator.calculate_dps(ap_attributes)
            ap_dps_curve.append({'x': i, 'y': dps_gain['total']})
            if 0 < i < 101:
                for ability, damage_gain in dps_gain.items():
                    if ability == 'total': continue
                    if ability not in ap_details_by_ability:
                        ap_details_by_ability[ability] = {}
                    ap_details_by_ability[ability][f'+{i} AP'] = damage_gain
        
        ap_details_table = []
        all_abilities_ap = sorted(list(ap_details_by_ability.keys()))
        for ability in all_abilities_ap:
            row = {'ability': ability}
            row.update(ap_details_by_ability[ability])
            ap_details_table.append(row)

        # Calculate weapon skill DPS curves using AttackTableDamageCalculator
        mh_skill_dps_curve = []
        oh_skill_dps_curve = []
        skill_attributes = EMPTY_ATTRIBUTES.copy()
        for i in range(0, 16):  # Simulate for +0 to +15 skill
            # Main-hand skill
            skill_attributes['mainHandSkill'] = i
            skill_attributes['offHandSkill'] = 0
            dps_gain_mh = damage_calculator.calculate_dps(skill_attributes)
            mh_skill_dps_curve.append({'x': i, 'y': dps_gain_mh['total']})
            # logging.info(f"Main-hand DPS (+{i}% skills) simulation result :{dps_gain_mh['total']}")

            # Off-hand skill
            skill_attributes['mainHandSkill'] = 0
            skill_attributes['offHandSkill'] = i
            dps_gain_oh = damage_calculator.calculate_dps(skill_attributes)
            oh_skill_dps_curve.append({'x': i, 'y': dps_gain_oh['total']})
            # logging.info(f"Off-hand DPS (+{i}% skills) simulation result :{dps_gain_oh['total']}")

        # Calculate Crit/Hit DPS gain details
        crit_details_by_ability = {}
        hit_details_by_ability = {}
        # Calculate total skill DPS curve
        total_skill_dps_curve = []
        for i in range(len(mh_skill_dps_curve)):
            mh_point = mh_skill_dps_curve[i]
            oh_point = oh_skill_dps_curve[i]
            total_y = mh_point['y'] + oh_point['y']
            total_skill_dps_curve.append({'x': mh_point['x'], 'y': total_y})

        crit_dps_curve = []
        crit_attributes = EMPTY_ATTRIBUTES.copy()
        for i in range(0, 16, 1):
            crit_attributes['crit'] = i
            dps_gain = damage_calculator.calculate_dps(crit_attributes)
            crit_dps_curve.append({'crit': i, 'dps': dps_gain['total']})
            # logging.info(f"Crit DPS (+{i}% crits) simulation result :{dps_gain['total']}")
            if 1 <= i <= 10:
                for ability, damage_gain in dps_gain.items():
                    if ability == 'total': continue
                    if ability not in crit_details_by_ability:
                        crit_details_by_ability[ability] = {}
                    crit_details_by_ability[ability][f'{i}%'] = damage_gain

        hit_dps_curve = []
        hit_attributes = EMPTY_ATTRIBUTES.copy()
        for i in range(0, 16, 1):
            hit_attributes['hit'] = i
            dps_gain = damage_calculator.calculate_dps(hit_attributes)
            hit_dps_curve.append({'hit': i, 'dps': dps_gain['total']})
            logging.debug(f"Hit DPS (+{i}% hit) simulation result :{dps_gain}")
            if 1 <= i <= 10:
                for ability, damage_gain in dps_gain.items():
                    if ability == 'total': continue
                    if ability not in hit_details_by_ability:
                        hit_details_by_ability[ability] = {}
                    hit_details_by_ability[ability][f'{i}%'] = damage_gain

        # Combine crit and hit curves
        for i, crit_point in enumerate(crit_dps_curve):
            if i < len(hit_dps_curve):
                hit_dps_curve[i]['crit_dps'] = crit_point['dps']
        
        # Format for frontend table
        crit_details_table = []
        all_abilities_crit = sorted(list(crit_details_by_ability.keys()))
        for ability in all_abilities_crit:
            row = {'ability': ability}
            row.update(crit_details_by_ability[ability])
            crit_details_table.append(row)

        hit_details_table = []
        all_abilities_hit = sorted(list(hit_details_by_ability.keys()))
        for ability in all_abilities_hit:
            row = {'ability': ability}
            row.update(hit_details_by_ability[ability])
            hit_details_table.append(row)

        # Calculate Weapon Skill DPS gain details
        mh_skill_details_by_ability = {}
        oh_skill_details_by_ability = {}
        skill_detail_steps = range(1, 16) # +1 to +15 skill

        for i in skill_detail_steps:
            # MH Skill details
            skill_attributes = EMPTY_ATTRIBUTES.copy()
            skill_attributes['mainHandSkill'] = i
            gains_mh = damage_calculator.calculate_dps(skill_attributes)
            for ability, damage_gain in gains_mh.items():
                if 1 <= i <= 10:
                    if ability == 'total': continue
                    if ability not in mh_skill_details_by_ability:
                        mh_skill_details_by_ability[ability] = {}
                    mh_skill_details_by_ability[ability][f'+{i} Skill'] = damage_gain

            # OH Skill details
            skill_attributes = EMPTY_ATTRIBUTES.copy()
            skill_attributes['offHandSkill'] = i
            gains_oh = damage_calculator.calculate_dps(skill_attributes)
            for ability, damage_gain in gains_oh.items():
                if 1 <= i <= 10:
                    if ability == 'total': continue
                    if ability not in oh_skill_details_by_ability:
                        oh_skill_details_by_ability[ability] = {}
                    oh_skill_details_by_ability[ability][f'+{i} Skill'] = damage_gain

        skill_attributes['mainHandSkill'] = -4
        skill_attributes['offHandSkill'] = 0
        gains_mh = damage_calculator.calculate_dps(skill_attributes)

        # Format for frontend
        mh_skill_details_table = []
        all_abilities_mh = sorted(list(mh_skill_details_by_ability.keys()))
        for ability in all_abilities_mh:
            row = {'ability': ability}
            row.update(mh_skill_details_by_ability[ability])
            mh_skill_details_table.append(row)

        oh_skill_details_table = []
        all_abilities_oh = sorted(list(oh_skill_details_by_ability.keys()))
        for ability in all_abilities_oh:
            row = {'ability': ability}
            row.update(oh_skill_details_by_ability[ability])
            oh_skill_details_table.append(row)

        result = {
            'damage_breakdown': damage_summary_df.to_dict(orient='records'),
            'dps_curves': {
                'attack_power': ap_dps_curve,
                'weapon_skill': {
                    'mh': mh_skill_dps_curve,
                    'oh': oh_skill_dps_curve,
                    'total': total_skill_dps_curve
                },
                'hit_crit': hit_dps_curve
            },
            'dps_gain_details': {
                'attack_power': ap_details_table,
                'crit': crit_details_table,
                'hit': hit_details_table,
                'weapon_skill': {
                    'mh': mh_skill_details_table,
                    'oh': oh_skill_details_table
                }
            }
        }

        return jsonify(result)
        
    except Exception as e:
        app.logger.error(f"Error during analysis for report {report_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/dps_simulation_stack', methods=['POST'])
def dps_simulation_stack():
    data = request.json
    report_id = data.get('report_id')
    fight_id = int(data.get('fight_id'))
    player_id = int(data.get('player_id'))
    current_status = data.get('current_status', {})
    attributes = data.get('attributes', {})

    try:
        # Get the damage breakdown from the actual WCL data
        analysis_result = run_full_analysis(report_id, fight_id, player_id, current_status)
        events = analysis_result['events']
        fight_duration = analysis_result['fight_duration']
        buff_multipliers = analysis_result['buff_multipliers']
        ability_stats = analysis_result['ability_stats']
        boss_list = analysis_result['boss_list']
        character_faction = analysis_result['character_faction']

        # Initialize calculator
        damage_calculator = AttackTableDamageCalculator(
            boss_list=boss_list,
            events=events,
            fight_duration=fight_duration,
            buff_multipliers=buff_multipliers,
            ability_stats=ability_stats,
            current_status=current_status,
            attributes=attributes,
            character_faction=character_faction
        )

        # Use attributes from the request
        sim_attributes = {
            "Strength": {"strength": attributes.get("strength", 0)},
            "Agility": {"agility": attributes.get("agility", 0)},
            "Attack Power": {"attackPower": attributes.get("attackPower", 0)},
            "Haste": {"haste": attributes.get("haste", 0)},
            "Crit": {"crit": attributes.get("crit", 0)},
            "Hit": {"hit": attributes.get("hit", 0)},
            "Weapon Skill (MH)": {"mainHandSkill": attributes.get("mainHandSkill", 0)},
            "Weapon Skill (OH)": {"offHandSkill": attributes.get("offHandSkill", 0)}
        }

        dps_stack_data = {
            "individual_gains": [],
            "total_gains": {}
        }

        # First, calculate the total gain from all attributes combined
        total_dps_gain = damage_calculator.calculate_dps(attributes)
        total_dps_gain.pop('total', 0) # Remove the sum total, we only need ability breakdown
        dps_stack_data["total_gains"] = total_dps_gain

        # Then, calculate the gain for each attribute individually
        for attr_name, attr_values in sim_attributes.items():
            # Skip if the attribute value is 0
            if list(attr_values.values())[0] == 0:
                continue
            
            temp_attributes = EMPTY_ATTRIBUTES.copy()
            temp_attributes.update(attr_values)
            
            dps_gain = damage_calculator.calculate_dps(temp_attributes)
            
            total_gain = dps_gain.pop('total', 0)
            
            dps_stack_data["individual_gains"].append({
                "attribute": attr_name,
                "total_dps_gain": total_gain,
                "ability_gains": dps_gain
            })

        return jsonify(dps_stack_data)

    except Exception as e:
        app.logger.error(f"Error during DPS stack simulation for report {report_id}: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
