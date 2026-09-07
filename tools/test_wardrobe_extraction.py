#!/usr/bin/env python3
import importlib.util
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROM_PATH = Path(os.environ.get('GRAVEBLOOD_ROM', '/mnt/data/Graveblood 0.0.1.1.5.2 demo.gba'))
SPEC = importlib.util.spec_from_file_location('extract_extended_semantics', ROOT / 'tools' / 'extract_extended_semantics.py')
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

STRUCT_SPEC = importlib.util.spec_from_file_location('extract_structure', ROOT / 'tools' / 'extract_structure.py')
struct_mod = importlib.util.module_from_spec(STRUCT_SPEC)
STRUCT_SPEC.loader.exec_module(struct_mod)


class WardrobeExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_player_constructor_wardrobe_table_is_ten_fixed_20_byte_slots(self):
        rows = mod.extract_wardrobe_labels(self.data)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0]['label'], 'Favorite Skirt')
        self.assertEqual([r['label'].strip() for r in rows[1:8]], ['Not for demo'] * 7)
        self.assertEqual([r['label'] for r in rows[8:]], ['', ''])
        self.assertEqual(rows[0]['source_rom_addr'], '0x080198A0')
        self.assertEqual(rows[9]['source_rom_addr'], '0x08019954')
        self.assertEqual(rows[0]['player_object_offset'], '+0x2B4')
        self.assertEqual(rows[9]['player_object_offset'], '+0x368')


class SpawnFactoryExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_latest_spawn_registry_resolves_runtime_classes_and_allocations(self):
        rows = mod.extract_spawn_factories(self.data)
        by_name = {row['spawn_type']: row for row in rows}
        self.assertEqual(set(by_name), {'npc', 'grass', 'fgtile'})

        npc = by_name['npc']
        self.assertEqual(npc['registration_function'], '0x0800D968')
        self.assertEqual(npc['factory'], '0x08003A60')
        self.assertEqual(npc['allocation_bytes'], '0xFC')
        self.assertEqual(npc['constructor'], '0x08003998')
        self.assertEqual(npc['vtable'], '0x08018B00')

        grass = by_name['grass']
        self.assertEqual(grass['factory'], '0x08002914')
        self.assertEqual(grass['allocation_bytes'], '0x6C')
        self.assertEqual(grass['vtable'], '0x08018AD8')

        fgtile = by_name['fgtile']
        self.assertEqual(fgtile['registration_function'], '0x0800DBB4')
        self.assertEqual(fgtile['factory'], '0x08003AEC')
        self.assertEqual(fgtile['allocation_bytes'], '0x90')
        self.assertEqual(fgtile['vtable'], '0x08018E4C')

    def test_story_entity_overlay_slots_point_to_same_16_record_block(self):
        rows = mod.extract_story_entity_overlay_slots(self.data)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['slot_iwram'] for row in rows], ['0x0300083C', '0x03000840'])
        self.assertEqual([row['actor_list_ptr'] for row in rows], ['0x08018E94', '0x08018E94'])
        self.assertTrue(all(row['loader_function'] == '0x080010A4' for row in rows))
        self.assertTrue(all(row['level_gate_function'] == '0x080043AC' for row in rows))

    def test_npc_sprite_pipeline_exports_correct_initialized_source_base(self):
        rows = mod.extract_npc_sprite_pipeline(self.data)
        by_fact = {row['fact']: row for row in rows}
        self.assertEqual(by_fact['source_bias_iwram']['value'], '0x030007FC')
        self.assertEqual(by_fact['source_bias_initializer_rom']['value'], '0x08A8D7AC')
        self.assertEqual(by_fact['source_bias_initialized_value']['value'], '0xE00')
        self.assertEqual(by_fact['draw']['value'], '0x0800274C')
        self.assertIn('legsColor*8', by_fact['source_base_formula']['value'])


class State4ProgressionExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_state4_collection_selector_maps_five_collection_steps(self):
        rows = mod.extract_state4_collection_selector(self.data)
        self.assertEqual([row["progress_index"] for row in rows], list(range(6)))
        self.assertEqual([row["dialogue_script"] for row in rows], [4, -1, -1, 5, 6, 0])
        self.assertEqual(rows[3]["script_role"], "rusty key dialogue")
        self.assertEqual(rows[4]["script_role"], "final sketch / monster transition")
        self.assertEqual(rows[0]["selector_global"], "0x03000620")

    def test_contextual_dialogue_opcode_table_separates_normal_and_state4_semantics(self):
        rows = mod.extract_dialogue_context_semantics()
        keyed = {(row["context"], row["opcode"]): row for row in rows}
        self.assertEqual(keyed[("normal", -4)]["target"], "0x030006AC")
        self.assertIn("record argument", keyed[("normal", -4)]["proven_behavior"])
        self.assertEqual(keyed[("state4_pickup", -4)]["target"], "0x0300061C")
        self.assertIn("sets 1", keyed[("state4_pickup", -4)]["proven_behavior"])
        self.assertEqual(keyed[("state4_pickup", -5)]["target"], "0x080037F6")
        self.assertNotEqual(keyed[("normal", -5)]["semantic"], keyed[("state4_pickup", -5)]["semantic"])


class V4StoryAndGateSemanticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ROM_PATH.read_bytes()

    def test_story_entity_identity_export_is_conservative_and_evidence_backed(self):
        rows = mod.extract_story_entity_identities()
        keyed = {row["index"]: row for row in rows}
        self.assertEqual(len(rows), 16)
        self.assertEqual(keyed[4]["identity"], "IQ 54")
        self.assertEqual(keyed[4]["identity_confidence"], "high")
        self.assertIn("dial=2", keyed[4]["evidence"])
        self.assertEqual(keyed[10]["identity"], "Katya")
        self.assertIn("dial=3", keyed[10]["evidence"])
        self.assertEqual([keyed[i]["semantic_role"] for i in range(11, 16)], ["collection pickup"] * 5)
        self.assertTrue(all(keyed[i]["identity"] == "unidentified" for i in (0, 1, 2, 3, 5, 6, 7, 8, 9)))

    def test_level10_gate_policy_switches_exactly_after_rusty_key_progress(self):
        rows = mod.extract_level10_collection_gate_policy(self.data)
        by_phase = {row["phase"]: row for row in rows}
        self.assertEqual(by_phase["pre_key"]["progress_condition"], "<= 3")
        self.assertEqual(by_phase["pre_key"]["entry"], "0x08003BE6")
        self.assertIn("return", by_phase["pre_key"]["proven_behavior"])
        self.assertEqual(by_phase["post_key"]["progress_condition"], "> 3")
        self.assertEqual(by_phase["post_key"]["entry"], "0x0800404A")
        self.assertIn("interaction", by_phase["post_key"]["proven_behavior"])
        self.assertEqual(by_phase["post_key"]["selector_global"], "0x03000620")
        self.assertEqual(by_phase["post_key"]["affected_level10_tiles"], "4")

    def test_dialogue_script_csv_labels_are_normal_context_not_universal(self):
        self.assertIn("normal context", struct_mod.dialogue_opcode_interpretation(-4))
        self.assertIn("0x030006AC", struct_mod.dialogue_opcode_interpretation(-4))
        self.assertIn("normal context", struct_mod.dialogue_opcode_interpretation(-5))
        self.assertIn("0x08005720", struct_mod.dialogue_opcode_interpretation(-5))
        self.assertNotIn("final-sketch", struct_mod.dialogue_opcode_interpretation(-5).lower())

    def test_v4_known_symbol_source_of_truth_matches_contextual_semantics(self):
        funcs = {addr: (name, evidence) for addr, name, evidence in struct_mod.KNOWN_FUNCTIONS}
        globs = {addr: (name, evidence) for addr, name, evidence in struct_mod.KNOWN_GLOBALS}
        self.assertEqual(funcs[0x08003B98][0], "Fgtile_update")
        self.assertEqual(funcs[0x080037F6][0], "state4_final_collection_handler")
        self.assertEqual(funcs[0x080068BC][0], "Player_draw_state4_monster_branch")
        self.assertEqual(globs[0x0300061C][0], "state4_monster_render_flag")
        self.assertEqual(globs[0x03000620][0], "state4_collection_progress_index")
        self.assertIn("normal-context", globs[0x030006AC][1])


if __name__ == '__main__':
    unittest.main()
