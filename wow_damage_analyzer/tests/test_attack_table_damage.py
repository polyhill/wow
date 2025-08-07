import unittest
from decimal import Decimal
import sys
import os
import logging

logging.basicConfig(level=logging.DEBUG)

# Add the parent directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from attack_table_damage import AttackTableDamageCalculator

BASE_DAMAGE = Decimal(1000)

class TestAttackTableDamageCalculator(unittest.TestCase):

    def setUp(self):
        """Set up a common test environment for all tests."""
        self.boss_list = [{'id': 1}]
        # Base events are all normal hits (hitType: 1)
        self.base_events = [
            {'type': 'damage', 'ability': {'name': 'Melee'}, 'hand': 'main', 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 1},
            {'type': 'damage', 'ability': {'name': 'Melee'}, 'hand': 'off', 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 2},
            {'type': 'damage', 'ability': {'name': 'Bloodthirst'}, 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 3},
            {'type': 'damage', 'ability': {'name': 'Whirlwind'}, 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 4},
            {'type': 'damage', 'ability': {'name': 'Heroic Strike'}, 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 6},
            {'type': 'damage', 'ability': {'name': 'Execute'}, 'hitType': 1, 'amount': BASE_DAMAGE, 'damage_multiplier': Decimal('1.0'), 'timestamp': 10},
        ]
        self.fight_duration = 10
        self.buff_multipliers = {}
        self.ability_stats = {
            'main': {'avg_hit_damage': BASE_DAMAGE},
            'off': {'avg_hit_damage': BASE_DAMAGE},
            'Bloodthirst': {'avg_hit_damage': BASE_DAMAGE},
            'Whirlwind': {'avg_hit_damage': BASE_DAMAGE},
            'Execute': {'hit': 1, 'crit': 0, 'attacks': 1},
            'Heroic Strike': {'hit': 1, 'crit': 0, 'attacks': 1},
        }
        self.current_status = {
            'mh_skill': 305,
            'oh_skill': 305,
            'main_hand_speed': 2.4,
            'off_hand_speed': 1.8,
            'hit': 9,
            'crit': 30,
        }
        self.character_faction = 'Alliance'

    def _create_events_with_hittype(self, hit_type, abilities=None):
        """Creates a list of events with a specific hitType for given abilities."""
        # If abilities is None, apply to all abilities in base_events
        if abilities is None:
            abilities_in_events = {event['ability']['name'] for event in self.base_events}
            abilities = list(abilities_in_events)
        
        events = []
        for event in self.base_events:
            new_event = event.copy()
            if new_event['ability']['name'] in abilities:
                new_event['hitType'] = hit_type
            events.append(new_event)
        return events

    def _run_dps_calculation(self, attributes, events):
        """Helper to run DPS calculation."""
        calculator = AttackTableDamageCalculator(
            self.boss_list, events, self.fight_duration, self.buff_multipliers,
            self.ability_stats, self.current_status, attributes, self.character_faction
        )
        return calculator.calculate_dps()

    def _test_dps_change_for_normal_hits(self, attributes, assertion_method, assert_values_map=None):
        """Helper method to test DPS changes for various normal hit types."""
        if assert_values_map is None:
            assert_values_map = {}

        logging.debug(f"-----------Testing attributes({attributes})-----------")
        dps_map = {}
        for hit_type in [0, 1, 2, 4, 6, 7, 8]:
            assert_values = assert_values_map.get(hit_type, {})
            logging.debug(f"-----------Testing events which are all normal hits (hitType: {hit_type})-----------")
            dps = self._run_dps_calculation(attributes, self._create_events_with_hittype(hit_type))
            dps_map[hit_type] = {}
            for ability, value in dps.items():
                ability_value = assert_values.get(ability, Decimal(0))
                dps_map[hit_type][ability] = value
                logging.debug(f"DPS for {ability} was {value}")
                assertion_method(value.quantize(Decimal('0.0001')), ability_value.quantize(Decimal('0.0001')), f"DPS for {ability} with normal hits should be {assertion_method} to {ability_value}, but was {value}")
            logging.debug("------------------------------TEST END-------------------------------------")
        return dps_map

    def test_positive_skill_change(self):
        """Test that a positive change in weapon skill results in increases DPS for normal hits."""
        last_dps_map = {}
        for i in range(1, 11):
            attributes = {'mainHandSkill': i, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)
            
        last_dps_map = {}
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': i, 'attackPower': 0, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)

    def test_negative_skill_change(self):
        """Test that a negative change in weapon skill results in negative DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': -i, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)
            
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': -i, 'attackPower': 0, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)

    def test_positive_crit_change(self):
        """Test that a positive change in crit results in positive DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': i, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)
            
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': i, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)

    def test_negative_crit_change(self):
        """Test that a negative change in crit results in negative DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': -i, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)
            
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': -i, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)

    def test_positive_hit_change(self):
        """Test that a positive change in hit results in positive DPS when events are misses."""
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)
            
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)

    def test_negative_hit_change(self):
        """Test that a negative change in hit results in negative DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': -i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)
            
        last_dps_map = { }
        for i in range(1, 11):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': -i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)

    def test_positive_ap_change(self):
        """Test that a positive change in ap results in positive DPS when events are misses."""
        last_dps_map = { }
        for i in range(10, 200, 10):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': i, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)

    def test_negative_ap_change(self):
        """Test that a negative change in ap results in negative DPS for normal hits."""
        last_dps_map = { }
        for i in range(10, 200, 10):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': -i, 'crit': 0, 'hit': 0}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertLessEqual, assert_values_map=last_dps_map)

    def test_positive_haste_change(self):
        """Test that a positive change in haste results in positive DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 15):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': 0, 'haste': i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)

    def test_negative_haste_change(self):
        """Test that a negative change in haste results in negative DPS for normal hits."""
        last_dps_map = { }
        for i in range(1, 15):
            attributes = {'mainHandSkill': 0, 'offHandSkill': 0, 'attackPower': 0, 'crit': 0, 'hit': 0, 'haste': i}
            last_dps_map = self._test_dps_change_for_normal_hits(attributes, self.assertGreaterEqual, assert_values_map=last_dps_map)


if __name__ == '__main__':
    unittest.main()
