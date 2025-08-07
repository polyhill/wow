# -*- coding: utf-8 -*-
import logging
from decimal import Decimal, getcontext

getcontext().prec = 10

class AttackTableDamageCalculator:
    """
    A class to calculate damage based on the WoW attack table, using WCL fight analysis data.
    This calculator simulates the effect of changing character attributes on overall DPS
    by recalculating the outcomes of combat events based on a new attack table.
    """
    # --- Constants ---
    BLOODTHIRST_AP_SCALING = Decimal('0.45')  # Bloodthirst damage scaling factor with Attack Power.
    CRIT_MULTIPLIER_ABILITIES = Decimal('2.2')  # Critical strike damage multiplier for abilities (with talent).
    CRIT_MULTIPLIER_MELEE = Decimal('2.0')  # Standard critical strike damage multiplier for melee attacks.
    OFF_HAND_DAMAGE_COEFFICIENT = Decimal('0.625')  # Damage coefficient for off-hand weapon attacks (with talent).
    MELEE_GLANCE_RATE = Decimal('0.40')  # Fixed rate of glancing blows against a level 63 mob.
    # Rage generation formula for a level 60 character: (damage * 2.5) / (level * 22.5 + 270) -> damage / 30.747
    RAGE_CONVERSION_FACTOR = Decimal('30.747')  # Factor to convert damage done into rage generated.
    EXECUTE_DAMAGE_PER_RAGE = Decimal(15)  # Damage dealt by Execute per point of rage consumed.
    HEROIC_STRIKE_RAGE_COST = Decimal(12)  # Rage cost for Heroic Strike.
    HEROIC_STRIKE_DAMAGE_ADD = Decimal(157)  # Additional damage granted by Heroic Strike.
    DEATH_WISH_MULTIPLIER = Decimal('1.2')  # Damage multiplier from the Death Wish talent.

    def __init__(self, boss_list, events, fight_duration, buff_multipliers, ability_stats, current_status, attributes, character_faction):
        """
        Initializes the calculator with WCL fight analysis data and new character attributes.

        :param boss_list: A list of boss NPCs in the encounter.
        :param events: A list of all combat events from the WCL report.
        :param fight_duration: The total duration of the fight in seconds.
        :param buff_multipliers: A dictionary of uptime percentages for various buffs.
        :param ability_stats: A dictionary containing statistics for each ability used (e.g., average damage).
        :param current_status: The character's current stats before applying new attributes.
        :param attributes: The new attributes to be applied for the simulation (e.g., from new gear).
        :param character_faction: The faction of the character ('Alliance' or 'Horde').
        """
        self.boss_ids = [boss['id'] for boss in boss_list]
        self.events = events
        self.fight_duration = Decimal(fight_duration)
        self.buff_multipliers = buff_multipliers
        self.ability_stats = ability_stats
        self.character_faction = character_faction
        
        self.mh_skill = Decimal(current_status.get('mh_skill', 300))
        self.oh_skill = Decimal(current_status.get('oh_skill', 300) )       
        self.mh_speed = Decimal(current_status.get('main_hand_speed', 2.4))
        self.oh_speed = Decimal(current_status.get('off_hand_speed', 1.8))
        self.current_hit = Decimal(current_status.get('hit', 10)) / Decimal(100)
        self.current_crit = Decimal(current_status.get('crit', 45)) / Decimal(100)

        self.base_damage_multiplier = self.buff_multipliers.get('sayges_dark_fortune', 1.0)

        bless = Decimal('1.1') if character_faction == 'Alliance' else Decimal(1);
        self.attribute_multiplier = Decimal(self.buff_multipliers.get('spirit_of_zandalar', Decimal('1.0'))) * bless
        self.death_wish_uptime = self.buff_multipliers.get('death_wish_uptime', [])
        self.recklessness_uptime = self.buff_multipliers.get('recklessness_uptime', [])

        self.attributes = attributes

        self._classify_phase()
        # Calculate and store the default attack tables based on initial attributes.
        self.attack_tables = self._calculate_attack_tables(self.attributes)

    def is_alliance(self):
        return self.character_faction == 'Alliance'

    def _classify_phase(self):
        """
        Identifies the start time of the execute phase (when the boss is below 20% health).
        This is used to determine when Execute can be used.
        """
        for e in self.events:
            if e.get('type') == 'damage' and e.get('targetID') in self.boss_ids:
                hitPoints = e.get('hitPoints')
                maxHitPoints = e.get('maxHitPoints')
                if hitPoints and maxHitPoints and hitPoints/maxHitPoints <= 0.2:
                    self.execute_start_time = e.get('timestamp')
                    break
    
    def is_executing(self, event):
        """
        Checks if a given combat event occurred during the execute phase.

        :param event: The combat event to check.
        :return: True if the event is in the execute phase, False otherwise.
        """
        timestamp = event.get('timestamp', 0)
        if timestamp != 0 and hasattr(self, 'execute_start_time') and timestamp >= self.execute_start_time:
            return True
        else:
            return False

    def is_recklessness(self, event):
        """
        Checks if a given combat event occurred while Recklessness was active.

        :param event: The combat event to check.
        :return: True if Recklessness was active, False otherwise.
        """
        timestamp = event.get('timestamp', 0)
        for start, end in self.recklessness_uptime:
            if start <= timestamp <= end:
                return True
        return False

    def _get_glance_penalty(self, weapon_skill):
        """
        Calculates the glancing blow damage penalty based on weapon skill against a level 63 mob.
        """
        # The penalty starts at 35% for 300 weapon skill and is reduced by 4% for each skill point up to 308.
        skill_diff = weapon_skill - 300
        penalty_reduction = max(min(skill_diff, 8), -5) * Decimal('0.04')
        penalty = Decimal('0.35') - penalty_reduction
        return max(penalty, Decimal('0.05'))

    def get_damage_multipier(self, event):
        """
        Calculates the total damage multiplier for a given event based on active buffs.

        :param event: The combat event.
        :return: The total damage multiplier.
        """
        timestamp = event.get('timestamp', 0)
        # Apply global damage multipliers
        damage_gain = self.base_damage_multiplier
        for start, end in self.death_wish_uptime:
            if start <= timestamp <= end:
                damage_gain *= self.DEATH_WISH_MULTIPLIER
                break
        return damage_gain

    def _calculate_attack_tables(self, attributes):
        """
        Calculates the attack table probabilities (hit, crit, miss, dodge, etc.)
        based on the character's base stats plus the provided attributes.
        This method is thread-safe as it does not modify instance state.
        :param attributes: A dictionary of attributes to use for the calculation.
        :return: A dictionary containing all calculated attack tables.
        """
        main_weapon_skill = Decimal(self.mh_skill) + Decimal(attributes.get('mainHandSkill', 0))
        off_weapon_skill = Decimal(self.oh_skill) + Decimal(attributes.get('offHandSkill', 0))

        glance_rate = self.MELEE_GLANCE_RATE
        panel_hit_rate = self.current_hit + (Decimal(attributes.get('hit', 0)) / Decimal('100'))
        panel_crit_rate = self.current_crit + (Decimal(attributes.get('crit', 0)) / Decimal('100'))
        
        boss_main_crit_rate = panel_crit_rate - Decimal('0.03') - max(Decimal('0'), (Decimal('315') - main_weapon_skill) * Decimal('0.0004'))
        boss_off_crit_rate = panel_crit_rate - Decimal('0.03') - max(Decimal('0'), (Decimal('315') - off_weapon_skill) * Decimal('0.0004'))        
        current_boss_main_crit_rate = self.current_crit - Decimal('0.03') - max(Decimal('0'), (Decimal('315') - Decimal(self.mh_skill)) * Decimal('0.0004'))
        current_boss_off_crit_rate = self.current_crit - Decimal('0.03') - max(Decimal('0'), (Decimal('315') - Decimal(self.oh_skill)) * Decimal('0.0004'))
        
        ability_miss_rate = max(Decimal('0'), ((Decimal('0.09') - (main_weapon_skill - Decimal('300')) * Decimal('0.004')) if main_weapon_skill < 305 else (Decimal('0.06') - (main_weapon_skill - Decimal('305')) * Decimal('0.001'))) - panel_hit_rate)
        dual_main_miss_rate = max(Decimal('0'), Decimal('0.19') + ((Decimal('0.09') - (main_weapon_skill - Decimal('300')) * Decimal('0.004')) if main_weapon_skill < 305 else (Decimal('0.06') - (main_weapon_skill - Decimal('305')) * Decimal('0.001'))) - panel_hit_rate)
        dual_off_miss_rate = max(Decimal('0'), Decimal('0.19') + ((Decimal('0.09') - (off_weapon_skill - Decimal('300')) * Decimal('0.004')) if off_weapon_skill < 305 else (Decimal('0.06') - (off_weapon_skill - Decimal('305')) * Decimal('0.001'))) - panel_hit_rate)
        
        current_ability_miss_rate = max(Decimal('0'), ((Decimal('0.09') - ( Decimal(self.mh_skill) - Decimal('300')) * Decimal('0.004')) if  Decimal(self.mh_skill) < 305 else (Decimal('0.06') - ( Decimal(self.mh_skill) - Decimal('305')) * Decimal('0.001'))) - self.current_hit)
        current_dual_main_miss_rate = max(Decimal('0'), Decimal('0.19') + ((Decimal('0.09') - ( Decimal(self.mh_skill) - Decimal('300')) * Decimal('0.004')) if  Decimal(self.mh_skill) < 305 else (Decimal('0.06') - ( Decimal(self.mh_skill) - Decimal('305')) * Decimal('0.001'))) - self.current_hit)
        current_dual_off_miss_rate = max(Decimal('0'), Decimal('0.19') + ((Decimal('0.09') - (Decimal(self.oh_skill) - Decimal('300')) * Decimal('0.004')) if Decimal(self.oh_skill) < 305 else (Decimal('0.06') - (Decimal(self.oh_skill) - Decimal('305')) * Decimal('0.001'))) - self.current_hit)
        # logging.info(f"current_ability_miss_rate: {current_ability_miss_rate} = max(0, (0.09 - ({self.mh_skill} - 300)) * 0.002) if  {self.mh_skill} < 305 else (0.06 - ({self.mh_skill} - 305) * 0.001)) - {self.current_hit})")

        dodge_rate = Decimal('0.065') - (main_weapon_skill - Decimal('300')) * Decimal('0.001')
        off_dodge_rate = Decimal('0.065') - (off_weapon_skill - Decimal('300')) * Decimal('0.001')
        current_dodge_rate = Decimal('0.065') - (Decimal(self.mh_skill) - Decimal('300')) * Decimal('0.001')
        current_off_dodge_rate = Decimal('0.065') - (Decimal(self.oh_skill) - Decimal('300')) * Decimal('0.001')

        parry_rate = Decimal('0.14') - (main_weapon_skill - Decimal('300')) * Decimal('0.001')
        off_parry_rate = Decimal('0.14') - (off_weapon_skill - Decimal('300')) * Decimal('0.001')
        current_parry_rate = Decimal('0.14') - (Decimal(self.mh_skill) - Decimal('300')) * Decimal('0.001')
        current_off_parry_rate = Decimal('0.14') - (Decimal(self.oh_skill) - Decimal('300')) * Decimal('0.001')

        block_rate = Decimal('0.05') if main_weapon_skill <= 315 else Decimal('0.05') - (main_weapon_skill - Decimal('315')) * Decimal('0.001')
        off_block_rate = Decimal('0.05') if off_weapon_skill <= 315 else Decimal('0.05') - (off_weapon_skill - Decimal('315')) * Decimal('0.001')
        current_block_rate = Decimal('0.05') if Decimal(self.mh_skill) <= 315 else Decimal('0.05') - (Decimal(self.mh_skill) - Decimal('315')) * Decimal('0.001')
        current_off_block_rate = Decimal('0.05') if Decimal(self.oh_skill) <= 315 else Decimal('0.05') - (Decimal(self.oh_skill) - Decimal('315')) * Decimal('0.001')
        
        ability_attack_table = Decimal('1.00') - dodge_rate - ability_miss_rate
        ability_crit_rate = min(ability_attack_table, boss_main_crit_rate)
        ability_hit_rate = max(Decimal('0'), ability_attack_table - ability_crit_rate)
        # logging.info(f"        dodge_rate: {dodge_rate:.3f},         ability_miss_rate:{ability_miss_rate:.3f},         ability_crit_rate:{ability_crit_rate:.3f},         ability_hit_rate:{ability_hit_rate:.3f}")

        current_ability_attack_table = Decimal('1.00') - current_dodge_rate - current_ability_miss_rate
        current_ability_crit_rate = min(current_ability_attack_table, current_boss_main_crit_rate)
        current_ability_hit_rate = max(Decimal('0'), current_ability_attack_table - current_ability_crit_rate)
        # logging.info(f"current_dodge_rate: {current_dodge_rate:.3f}, current_ability_miss_rate:{current_ability_miss_rate:.3f}, current_ability_crit_rate:{current_ability_crit_rate:.3f}, current_ability_hit_rate:{current_ability_hit_rate}")

        dual_main_attack_table = Decimal('1.00') - dodge_rate - glance_rate - dual_main_miss_rate
        main_crit_rate = min(dual_main_attack_table, boss_main_crit_rate)
        main_hit_rate = max(Decimal('0'), dual_main_attack_table - main_crit_rate)

        current_dual_main_attack_table = Decimal('1.00') - current_dodge_rate - glance_rate - current_dual_main_miss_rate
        current_main_crit_rate = min(current_dual_main_attack_table, current_boss_main_crit_rate)
        current_main_hit_rate = max(Decimal('0'), current_dual_main_attack_table - current_main_crit_rate)

        dual_off_attack_table = Decimal('1.00') - off_dodge_rate - glance_rate - dual_off_miss_rate
        off_crit_rate = min(dual_off_attack_table, boss_off_crit_rate)
        off_hit_rate = max(Decimal('0'), dual_off_attack_table - off_crit_rate)

        current_dual_off_attack_table = Decimal('1.00') - current_off_dodge_rate - glance_rate - current_dual_off_miss_rate
        current_off_crit_rate = min(current_dual_off_attack_table, current_boss_off_crit_rate)
        current_off_hit_rate = max(Decimal('0'), current_dual_off_attack_table - current_off_crit_rate)

        keeping_hs_dual_off_attack_table = Decimal('1.00') - off_dodge_rate - glance_rate
        keeping_hs_off_crit_rate = min(keeping_hs_dual_off_attack_table, boss_off_crit_rate)
        keeping_hs_off_hit_rate = max(Decimal('0'), keeping_hs_dual_off_attack_table - keeping_hs_off_crit_rate)

        current_keeping_hs_dual_off_attack_table = Decimal('1.00') - current_off_dodge_rate - glance_rate
        current_keeping_hs_off_crit_rate = min(current_keeping_hs_dual_off_attack_table, current_boss_off_crit_rate)
        current_keeping_hs_off_hit_rate = max(Decimal('0'), current_keeping_hs_dual_off_attack_table - current_keeping_hs_off_crit_rate)

        ability_rates = {
            'name': 'ability',
            'current_actual_hit': current_ability_hit_rate + current_ability_crit_rate,
            'new_actual_hit': ability_hit_rate + ability_crit_rate,
            'current_hit': current_ability_hit_rate,
            'current_crit': current_ability_crit_rate,
            'new_hit': ability_hit_rate,
            'new_crit': ability_crit_rate,
            'current_dodge': current_dodge_rate,
            'new_dodge': dodge_rate,
            'current_parry': current_parry_rate,
            'new_parry': parry_rate,
            'current_front_miss': current_block_rate + current_parry_rate + current_dodge_rate + ability_miss_rate,
            'new_front_miss': block_rate + parry_rate + dodge_rate + ability_miss_rate,
            'current_front_crit': min(current_ability_crit_rate, Decimal(1) - (current_block_rate + current_parry_rate + current_dodge_rate + ability_miss_rate)),
            'new_front_crit': min(ability_crit_rate, Decimal(1) - (block_rate + parry_rate + dodge_rate + ability_miss_rate)),
        }

        main_hand_rates = {
            'name': 'main',
            'current_actual_hit': current_main_hit_rate + current_main_crit_rate + glance_rate,
            'new_actual_hit': main_hit_rate + main_crit_rate + glance_rate,
            'current_hit': current_main_hit_rate,
            'current_crit': current_main_crit_rate,
            'new_hit': main_hit_rate,
            'new_crit': main_crit_rate,
            'current_dodge': current_dodge_rate,
            'new_dodge': dodge_rate,
            'current_parry': current_parry_rate,
            'new_parry': parry_rate,
            'current_front_miss': current_block_rate + current_parry_rate + current_dodge_rate + current_dual_main_miss_rate,
            'new_front_miss': block_rate + parry_rate + dodge_rate + dual_main_miss_rate,
            'current_front_crit': min(current_main_crit_rate, Decimal(1) - (current_block_rate + current_parry_rate + current_dodge_rate + current_dual_main_miss_rate)),
            'new_front_crit': min(main_crit_rate, Decimal(1) - (block_rate + parry_rate + dodge_rate + dual_main_miss_rate)),
            'current_glance_penalty': self._get_glance_penalty(Decimal(self.mh_skill)),
            'new_glance_penalty': self._get_glance_penalty(main_weapon_skill)
        }

        off_hand_rates = {
            'name': 'off',
            'current_actual_hit': current_off_hit_rate + current_off_crit_rate + glance_rate,
            'new_actual_hit': off_hit_rate + off_crit_rate + glance_rate,
            'current_hit': current_off_hit_rate,
            'current_crit': current_off_crit_rate,
            'new_hit': off_hit_rate,
            'new_crit': off_crit_rate,
            'current_dodge': current_off_dodge_rate,
            'new_dodge': off_dodge_rate,
            'current_parry': current_off_parry_rate,
            'new_parry': off_parry_rate,
            'current_front_miss': current_block_rate + current_parry_rate + current_dodge_rate + current_dual_off_miss_rate,
            'new_front_miss': block_rate + parry_rate + dodge_rate + dual_off_miss_rate,
            'current_front_crit': min(current_off_crit_rate, Decimal(1) - (current_block_rate + current_parry_rate + current_dodge_rate + current_dual_off_miss_rate)),
            'new_front_crit': min(off_crit_rate, Decimal(1) - (block_rate + parry_rate + dodge_rate + dual_off_miss_rate)),
            'current_glance_penalty': self._get_glance_penalty(Decimal(self.oh_skill)),
            'new_glance_penalty': self._get_glance_penalty(off_weapon_skill)
        }

        keeping_hs_off_hand_rates = {
            'name': 'keeping_hs_off',
            'current_actual_hit': current_keeping_hs_off_hit_rate + current_keeping_hs_off_crit_rate + glance_rate,
            'new_actual_hit': keeping_hs_off_hit_rate + keeping_hs_off_crit_rate + glance_rate,
            'current_hit': current_keeping_hs_off_hit_rate,
            'current_crit': current_keeping_hs_off_crit_rate,
            'new_hit': keeping_hs_off_hit_rate,
            'new_crit': keeping_hs_off_crit_rate,
            'current_dodge': current_off_dodge_rate,
            'new_dodge': off_dodge_rate,
            'current_parry': current_off_parry_rate,
            'new_parry': off_parry_rate,
            'current_front_miss': current_block_rate + current_parry_rate + current_dodge_rate + current_ability_miss_rate,
            'new_front_miss': block_rate + parry_rate + dodge_rate + ability_miss_rate,
            'current_front_crit': min(current_keeping_hs_off_crit_rate, Decimal(1) - (current_block_rate + current_parry_rate + current_dodge_rate + current_ability_miss_rate)),
            'new_front_crit': min(keeping_hs_off_crit_rate, Decimal(1) - (block_rate + parry_rate + dodge_rate + ability_miss_rate)),
            'current_glance_penalty': self._get_glance_penalty(Decimal(self.oh_skill)),
            'new_glance_penalty': self._get_glance_penalty(off_weapon_skill)
        }

        # logging.info(f"current ability attack table: dodge_rate({current_dodge_rate}) + ability_miss_rate({current_ability_miss_rate}) + ability_crit_rate({current_ability_crit_rate}) + ability_hit_rate({current_ability_hit_rate})")
        # logging.info(f"ability attack table: dodge_rate({dodge_rate}) + ability_miss_rate({ability_miss_rate}) + ability_crit_rate({ability_crit_rate}) + ability_hit_rate({ability_hit_rate})")
        # logging.info(f"current main melee attack table: dodge_rate({current_dodge_rate}) + glance_rate({glance_rate})+ dual_main_miss_rate({current_dual_main_miss_rate}) + main_crit_rate({current_main_crit_rate}) + main_hit_rate({current_main_hit_rate})")
        # logging.info(f"main melee attack table: dodge_rate({dodge_rate}) + glance_rate({glance_rate})+ dual_main_miss_rate({dual_main_miss_rate}) + main_crit_rate({main_crit_rate}) + main_hit_rate({main_hit_rate})")
        # logging.info(f"current off melee attack table: dodge_rate({current_off_dodge_rate}) + glance_rate({glance_rate})+ dual_off_miss_rate({current_dual_off_miss_rate}) + main_crit_rate({current_off_crit_rate}) + main_hit_rate({current_off_hit_rate})")
        # logging.info(f"off melee attack table: dodge_rate({off_dodge_rate}) + glance_rate({glance_rate})+ dual_off_miss_rate({dual_off_miss_rate}) + main_crit_rate({off_crit_rate}) + main_hit_rate({off_hit_rate})")
        
        return {
            'ability_rates': ability_rates,
            'main_hand_rates': main_hand_rates,
            'off_hand_rates': off_hand_rates,
            'keeping_hs_off_hand_rates': keeping_hs_off_hand_rates
        }
    
    def calculate_dps(self, attributes=None):
        """
        Calculates the total DPS increase by iterating through all combat events and applying
        the new simulated attack outcomes. This method is thread-safe.
        
        :param attributes: Optional. A dictionary of attributes to use for the calculation. 
                           If not provided, the attributes from initialization will be used.
        :return: A dictionary containing the DPS for each ability and the total DPS.
        """
        current_attributes = attributes.copy() if attributes is not None else self.attributes.copy()
        
        # Optimization: If all attribute values are zero, no change in DPS.
        if all(value == 0 for value in current_attributes.values()):
            return {
                'main_hand': Decimal(0), 'off_hand': Decimal(0), 'Bloodthirst': Decimal(0),
                'Whirlwind': Decimal(0), 'Heroic Strike': Decimal(0), 'RAGE_TO_HS': Decimal(0),
                'RAGE_TO_EXECUTE': Decimal(0), 'total': Decimal(0)
            }
        # Transform strength and agility to Attack Power and Crits.
        stat_multiplier = Decimal(1.1) if self.is_alliance() else Decimal(1)
        stat_multiplier *= self.buff_multipliers['spirit_of_zandalar']
        if 'strength' in current_attributes:
            current_attributes['attackPower'] += Decimal(current_attributes['strength']) * Decimal(2) * stat_multiplier
        if 'agility' in current_attributes: 
            current_attributes['crit'] += Decimal(current_attributes['agility']) * stat_multiplier / Decimal(20)

        attack_tables = self._calculate_attack_tables(current_attributes) if attributes is not None else self.attack_tables

        main_hand_dps_incr = Decimal(0)
        off_hand_dps_incr = Decimal(0)
        bloodthirst_dps_incr = Decimal(0)
        whirlwind_dps_incr = Decimal(0)
        execute_dps_incr = Decimal(0)
        hs_dps_incr = Decimal(0)
        hs_slots = []
        normal_melee_damage = Decimal(0)
        execute_melee_damage = Decimal(0)

        for e in self.events:
            if e.get('type') == 'damage' and e.get('ability') and e.get('hitType') in [0, 1, 2, 4, 6, 7, 8]:
                ability_name = e.get('ability').get('name')
                hand = e.get('hand')

                if ability_name == 'Melee' and hand == 'main':
                    melee_damage = self.calculate_main_melee_dps(e, current_attributes, attack_tables)
                    main_hand_dps_incr += melee_damage
                    if not self.is_executing(e):
                        hs_slots.insert(0, e)
                        normal_melee_damage += melee_damage
                    else:
                        execute_melee_damage += melee_damage
                elif ability_name == 'Melee' and hand == 'off':
                    melee_damage = self.calculate_off_melee_dps(e, current_attributes, attack_tables)
                    off_hand_dps_incr += melee_damage
                    if not self.is_executing(e):
                        normal_melee_damage += melee_damage
                    else:
                        execute_melee_damage += melee_damage
                elif ability_name == 'Bloodthirst':
                    bloodthirst_dps_incr += self.calculate_bloodthirst_dps(e, current_attributes, attack_tables)
                elif ability_name == 'Whirlwind':
                    whirlwind_dps_incr += self.calculate_whirlwind_dps(e, current_attributes, attack_tables)
                elif ability_name == 'Execute':
                    execute_dps_incr += self.calculate_execute_dps(e, current_attributes, attack_tables)
                elif ability_name == 'Heroic Strike':
                    hs_dps_incr += self.calculate_hs_dps(e, current_attributes, attack_tables)
        
        # Calculates the total DPS increase from haste
        if 'haste' in current_attributes:
            haste_multiplier = Decimal(current_attributes['haste']) / Decimal(100)
            main_hand_dps_incr += self.ability_stats['main']['_total_hit_damage'] * haste_multiplier
            off_hand_dps_incr += self.ability_stats['off']['_total_hit_damage'] * haste_multiplier
            hs_dps_incr += self.ability_stats['Heroic Strike']['_total_hit_damage'] * haste_multiplier
            normal_melee_damage *= (Decimal(1) + haste_multiplier)
            execute_melee_damage *= (Decimal(1) + haste_multiplier)

        result_damage = self._calc_rage_dps(self.ability_stats['main'], self.ability_stats['Execute'], hs_slots, normal_melee_damage, execute_melee_damage, attack_tables)
        
        damage = {
            'main_hand'     : main_hand_dps_incr   / self.fight_duration,
            'off_hand'      : off_hand_dps_incr    / self.fight_duration,
            'Bloodthirst'   : bloodthirst_dps_incr / self.fight_duration,
            'Whirlwind'     : whirlwind_dps_incr   / self.fight_duration,
            'Execute'       : execute_dps_incr     / self.fight_duration,
            'Heroic Strike' : hs_dps_incr          / self.fight_duration,
            'Heroic Strike (from Rage)' : result_damage['hs_damage_incr']      / self.fight_duration,
            'Execute (from Rage)' : result_damage['execute_damage_incr'] / self.fight_duration,
        }
        total = sum(damage.values())
        damage['total'] = total
        return damage
    
    # --- Event Type Checkers ---
    def is_actual_hit(self, event):
        """Checks if an event was a hit, crit, or glance."""
        return event.get('hitType') in [1, 2, 6]
    def is_hit(self, event):
        """Checks if an event was a normal hit."""
        return event.get('hitType') == 1
    def is_crit(self, event):
        """Checks if an event was a critical hit."""
        return event.get('hitType') == 2
    def is_glance(self, event):
        """Checks if an event was a glancing blow."""
        return event.get('hitType') == 6 and event.get('ability').get('name') == 'Melee'
    def is_dodge(self,event):
        """Checks if an event was a dodge."""
        return event.get('hitType') == 7
    def is_parry(self,event):
        """Checks if an event was a parry (attack from the front)."""
        return event.get('hitType') == 8
    def is_block(self, event):
        """Checks if an event was a block hit (attack from the front)."""
        return event.get('hitType') == 4
    
    def _calc_rage_dps(self, mh_stat, execute_stat, hs_slots, normal_melee_damage, execute_melee_damage, attack_tables):
        """
        Calculates the damage increase from converting rage generated from melee attacks
        into Heroic Strikes or Executes.
        """
        # Calculate the total rage available from normal melee attacks.
        retain_rage = normal_melee_damage / self.RAGE_CONVERSION_FACTOR
        
        ability_rates = attack_tables['ability_rates']
        main_hand_rates = attack_tables['main_hand_rates']
        ab_hit_damage = mh_hit_damage = Decimal(mh_stat['avg_hit_damage'])
        hs_hit_damage = mh_hit_damage + self.HEROIC_STRIKE_DAMAGE_ADD
        mh_avg_cast_unit = main_hand_rates['new_hit'] + self.CRIT_MULTIPLIER_MELEE * main_hand_rates['new_crit'] + (Decimal(1) - main_hand_rates['new_glance_penalty']) * self.MELEE_GLANCE_RATE
        hs_avg_cast_unit = ability_rates['new_hit'] + self.CRIT_MULTIPLIER_ABILITIES * ability_rates['new_crit']
        avg_main_got_rage = mh_avg_cast_unit * mh_hit_damage / self.RAGE_CONVERSION_FACTOR
        avg_hs_damage_incr = hs_avg_cast_unit * hs_hit_damage - mh_avg_cast_unit * mh_hit_damage

        hs_damage_incr = Decimal(0) if retain_rage.quantize(Decimal('0.00001')) >= 0 else (avg_hs_damage_incr * Decimal(retain_rage) / (self.HEROIC_STRIKE_RAGE_COST + avg_main_got_rage))
       
        # Iterate through main-hand swing events that are candidates for Heroic Strike.
        for event in hs_slots:
            # Rage generated by this specific swing.
            got_rage = Decimal(event.get('amount')) / self.RAGE_CONVERSION_FACTOR
            damage_multiplier = Decimal(event.get('damage_multiplier'))
            
            # If there's no more rage to spend, stop.
            if retain_rage.quantize(Decimal('0.00001')) <= 0:
                break
            # If there's not enough rage for a full Heroic Strike, calculate a partial one.
            # This simulates the last HS cast before running out of rage.
            elif retain_rage < self.HEROIC_STRIKE_RAGE_COST + avg_main_got_rage:
                hs_times = retain_rage / (self.HEROIC_STRIKE_RAGE_COST + avg_main_got_rage)
                retain_rage = Decimal(0)
                damage_incr = avg_hs_damage_incr * hs_times
            # If there is enough rage, replace the melee swing with a full Heroic Strike.
            else:
                retain_rage -= self.HEROIC_STRIKE_RAGE_COST + avg_main_got_rage
                damage_incr = avg_hs_damage_incr
                event['new_ability'] = 'Heroic Strike'  
              
            event['amount_add'] = damage_incr * damage_multiplier
            hs_damage_incr += damage_incr * damage_multiplier

        # Any remaining rage, plus rage generated during the execute phase, is converted to Execute damage.
        retain_rage += execute_melee_damage / self.RAGE_CONVERSION_FACTOR
        retain_rage = Decimal(0) if retain_rage.quantize(Decimal('0.00001')) <= 0 else retain_rage
        if Decimal(execute_stat['attacks']) is not None and Decimal(execute_stat['attacks']) != Decimal(0):
            execute_damage_incr = retain_rage * self.EXECUTE_DAMAGE_PER_RAGE * (execute_stat['hit'] + execute_stat['crit'] * self.CRIT_MULTIPLIER_ABILITIES) / Decimal(execute_stat['attacks'])
        else:
            execute_damage_incr = 0
        # logging.info(f"EXECUTE Rage: {retain_rage:.3f} += {execute_melee_damage:.3f} / {self.RAGE_CONVERSION_FACTOR}")
        return {
            'hs_damage_incr': hs_damage_incr,
            'execute_damage_incr': execute_damage_incr
        }
    
    def _calc_one_cast_dps(self, event, ab_stat, ap_hit_damage_incr, ability_rates):
        """
        Calculates the damage increase for a single ability cast based on the new attack table.
        """
        damage_multiplier = Decimal(event.get('damage_multiplier'))
        event_hit_damage = Decimal(event.get('amount')) / damage_multiplier
        ab_hit_damage = Decimal(ab_stat['avg_hit_damage']) if event.get('amount') == 0 else event_hit_damage
        simulation_glance_damage_percent = Decimal('0.65')
        simulation_glance_rate = Decimal(0)

        # If the original event was a normal hit, simulate the new outcome.
        # The new hit rate is proportional to the change in hit chance, capped at 100%.
        # The remaining portion of what was a hit becomes a crit.
        if self.is_hit(event):
            simulation_actual_hit_rate = min(Decimal(1), ability_rates['new_actual_hit'] / ability_rates['current_actual_hit'])
            crit_chance_increase = max(Decimal(0), ability_rates['new_crit'] - ability_rates['current_crit'])
            hit_to_crit_chance = crit_chance_increase / ability_rates['current_hit'] if ability_rates['current_hit'] > 0 else Decimal(0)
            simulation_crit_rate = min(Decimal(1), hit_to_crit_chance)
            simulation_hit_rate = Decimal(1) - simulation_crit_rate
            logging.debug(f"{event.get('ability').get('name')} was hit: simulation_hit_rate({simulation_hit_rate}), simulation_crit_rate({simulation_crit_rate}), ability_rates:{ability_rates}")
        # If the original event was a crit, simulate the new outcome.
        # With Recklessness, crits are guaranteed. Otherwise, the new crit rate is proportional to the change.
        # The base damage is normalized by dividing out the crit multiplier.
        elif self.is_crit(event):
            simulation_actual_hit_rate = min(Decimal(1), ability_rates['new_actual_hit'] / ability_rates['current_actual_hit'])
            simulation_crit_rate = Decimal(1) if self.is_recklessness(event) else min(Decimal(1), ability_rates['new_crit'] / ability_rates['current_crit'])
            simulation_hit_rate = Decimal(1) - simulation_crit_rate
            ab_hit_damage /= self.CRIT_MULTIPLIER_ABILITIES
            logging.debug(f"{event.get('ability').get('name')} was crit: simulation_actual_hit_rate({simulation_actual_hit_rate:.4f}), simulation_hit_rate({simulation_hit_rate}), simulation_crit_rate({simulation_crit_rate})")
        # If the original event was a glance, it remains a glance.
        # The damage penalty is updated based on the new weapon skill.
        # The base damage is normalized by dividing out the old glance penalty.
        elif self.is_glance(event):
            simulation_actual_hit_rate = Decimal(1)
            simulation_hit_rate = 0
            simulation_crit_rate = 0
            simulation_glance_rate = Decimal(1)
            simulation_glance_damage_percent = Decimal(1) - ability_rates['new_glance_penalty']
            ab_hit_damage /= (Decimal(1) - ability_rates['current_glance_penalty'])
            logging.debug(f"{event.get('ability').get('name')} was glance: simulation_glance_damage_percent({simulation_glance_damage_percent:.4f}), ab_hit_damage({ab_hit_damage:.4f}), current_glance_penalty({ability_rates['current_glance_penalty']})")
        # If the original event was a dodge, it could become a hit or crit with higher weapon skill.
        # The chance to overcome the dodge is proportional to the increase in actual hit chance.
        elif self.is_dodge(event):
            logging.debug(f"{event.get('ability').get('name')} was dodge: ability_rates({ability_rates})")
            simulation_actual_hit_rate = Decimal(1) - min(Decimal(1), ability_rates['new_dodge'] / ability_rates['current_dodge'])
            simulation_crit_rate = Decimal(1) if self.is_recklessness(event) else ability_rates['new_crit']
            simulation_hit_rate = Decimal(1) - simulation_crit_rate
            event_hit_damage = Decimal(0)
            logging.debug(f"{event.get('ability').get('name')} was dodge: simulation_actual_hit_rate({simulation_actual_hit_rate:.4f}), simulation_hit_rate({simulation_hit_rate}), simulation_crit_rate({simulation_crit_rate})")
        # If the original event was a parry, it could become a hit or crit with higher weapon skill.
        # The chance to overcome the parry is proportional to the reduction in front miss chance.
        elif self.is_parry(event):
            simulation_actual_dodge_rate = Decimal(1) - min(Decimal(1), ability_rates['new_parry'] / ability_rates['current_parry'])
            simulation_actual_hit_rate = simulation_actual_dodge_rate * (Decimal(1) - min(Decimal(1), ability_rates['new_front_miss'] / ability_rates['current_front_miss']))
            simulation_crit_rate = Decimal(1) if self.is_recklessness(event) else ability_rates['new_front_crit']
            simulation_hit_rate = Decimal(1) - simulation_crit_rate
            event_hit_damage = Decimal(0)
            logging.debug(f"{event.get('ability').get('name')} was parry: simulation_actual_hit_rate({simulation_actual_hit_rate:.4f}), simulation_hit_rate({simulation_hit_rate}), simulation_crit_rate({simulation_crit_rate})")
        # If the original event was a block, it remains a block but is treated as a normal hit for damage calculation.
        elif self.is_block(event):
            simulation_actual_hit_rate = Decimal(1)
            simulation_crit_rate = Decimal(0)
            simulation_hit_rate = Decimal(1)
        # If the original event was a miss, it could become a hit or crit with higher hit rating.
        # The chance to overcome the miss is proportional to the increase in actual hit chance.
        else:
            simulation_actual_hit_rate = Decimal(1) - min(Decimal(1), (Decimal(1) - ability_rates['new_actual_hit']) / (Decimal(1) - ability_rates['current_actual_hit']))
            simulation_crit_rate = Decimal(1) if self.is_recklessness(event) else ability_rates['new_crit']
            simulation_hit_rate = Decimal(1) - simulation_crit_rate
            event_hit_damage = Decimal(0)
            logging.debug(f"{event.get('ability').get('name')} was miss: simulation_actual_hit_rate({simulation_actual_hit_rate:.4f}), simulation_hit_rate({simulation_hit_rate}), simulation_crit_rate({simulation_crit_rate})")
        
        # Calculate the new base damage including the bonus from attack power.
        new_ab_hit_damage = ab_hit_damage + ap_hit_damage_incr
        # Calculate the weighted average damage multiplier from the simulated hit/crit/glance outcomes.
        damage_gain_unit = simulation_hit_rate + simulation_glance_damage_percent * simulation_glance_rate + self.CRIT_MULTIPLIER_ABILITIES * simulation_crit_rate
        logging.debug(f"damage_gain_unit[{event.get('ability').get('name')}-{event.get('hitType')}]: {damage_gain_unit:.3f} = {simulation_hit_rate:.3f} + {simulation_glance_damage_percent:.3f} * {simulation_glance_rate:.3f} + {self.CRIT_MULTIPLIER_ABILITIES} * {simulation_crit_rate:.3f}")
        # Calculate the final damage increase by comparing the new simulated damage to the original damage.
        damage_incr = new_ab_hit_damage * damage_gain_unit * simulation_actual_hit_rate  - event_hit_damage
        logging.debug(f"damage_incr[{event.get('ability').get('name')}-{event.get('hitType')}]: {damage_incr:.3f} = {new_ab_hit_damage:.3f} * {damage_gain_unit:.3f} * {simulation_actual_hit_rate:.3f}  - {event_hit_damage:.3f}")
        
        return damage_incr * damage_multiplier
    
    def calculate_bloodthirst_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for a Bloodthirst event."""
        ab_stat = self.ability_stats['Bloodthirst']
        ap_hit_damage_incr = self.BLOODTHIRST_AP_SCALING * Decimal(attributes['attackPower'])
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['ability_rates'])
    
    def calculate_whirlwind_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for a Whirlwind event."""
        ab_stat = self.ability_stats['Whirlwind']
        ap_hit_damage_incr = self.mh_speed * Decimal(attributes['attackPower']) / Decimal(14)
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['ability_rates'])
    
    def calculate_execute_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for a Heroic Strike event."""
        ab_stat = self.ability_stats['Execute']
        ap_hit_damage_incr = Decimal(0)
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['ability_rates'])
    
    def calculate_hs_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for a Heroic Strike event."""
        ab_stat = self.ability_stats['Heroic Strike']
        ap_hit_damage_incr = self.mh_speed * Decimal(attributes['attackPower']) / Decimal(14)
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['ability_rates'])
    
    def calculate_main_melee_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for a main-hand melee swing."""
        ab_stat = self.ability_stats['main']
        ap_hit_damage_incr = self.mh_speed * Decimal(attributes['attackPower']) / Decimal(14)
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['main_hand_rates'])
    
    def calculate_off_melee_dps(self, event, attributes, attack_tables):
        """Calculates the damage increase for an off-hand melee swing."""
        ab_stat = self.ability_stats['off']
        ap_hit_damage_incr = self.oh_speed * Decimal(attributes['attackPower']) / Decimal(14)
        off_hand_rates = attack_tables['off_hand_rates']
        if self.is_executing(event) or (self.is_hit(event) and off_hand_rates['current_hit'] == Decimal(0)):
            return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, attack_tables['keeping_hs_off_hand_rates'])
        return self._calc_one_cast_dps(event, ab_stat, ap_hit_damage_incr, off_hand_rates)
    

if __name__ == '__main__':
    pass
