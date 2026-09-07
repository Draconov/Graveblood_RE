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
        self.assertEqual(keyed[9]["identity"], "IQ 54")
        self.assertEqual(keyed[9]["identity_confidence"], "high")
        self.assertIn("level=10", keyed[9]["evidence"])
        self.assertIn("dial=2", keyed[9]["evidence"])
        self.assertEqual([keyed[i]["semantic_role"] for i in range(11, 16)], ["collection pickup"] * 5)
        self.assertTrue(all(keyed[i]["identity"] == "unidentified" for i in (0, 1, 2, 3, 5, 6, 7, 8)))

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
        self.assertIn("fresh A", by_phase["post_key"]["proven_behavior"])
        self.assertIn("does not read portTo", by_phase["post_key"]["proven_behavior"])

    def test_level10_post_key_gate_collision_geometry_is_exact_2x2_grid_overlap(self):
        row = mod.extract_level10_gate_collision_geometry(self.data)
        self.assertEqual(row["player_x_grid"], "(playerX-8px)>>11")
        self.assertEqual(row["player_y_grid"], "(playerY-24px)>>11")
        self.assertEqual(row["actor_x_grid"], "(actorX-8px)>>11")
        self.assertEqual(row["actor_y_grid"], "(actorY-16px)>>11")
        self.assertEqual(row["contact_condition"], "PX in {AX,AX+1} and PY in {AY,AY+1}")
        self.assertEqual(row["grid_cell_px"], 8)
        self.assertEqual(row["player_contact_flag"], "+0x1C0=1")
        self.assertEqual(row["fgtile_contact_flags"], "+0x8C=1; +0x8D=1")

    def test_level10_post_key_gate_forces_vertical_targets_without_requesting_scene(self):
        rows = mod.extract_level10_gate_forced_motion(self.data)
        keyed = {row["turn"]: row for row in rows}
        self.assertEqual(set(keyed), {4, 5})
        self.assertEqual(keyed[4]["target_x_px"], 826)
        self.assertEqual(keyed[4]["target_y_px"], 360)
        self.assertEqual(keyed[5]["target_x_px"], 826)
        self.assertEqual(keyed[5]["target_y_px"], 410)
        self.assertEqual(keyed[4]["trigger"], "fresh A press while overlapping post-key gate collision geometry")
        self.assertEqual(keyed[4]["helper"], "0x080080A4")
        self.assertEqual(keyed[4]["player_target_x_offset"], "+0x390")
        self.assertEqual(keyed[4]["player_target_y_offset"], "+0x394")
        self.assertEqual(keyed[4]["player_vertical_delta_offset"], "+0x1C")
        self.assertIn("clears +0x390/+0x394", keyed[4]["helper_behavior"])
        self.assertEqual(keyed[4]["generic_portal_handoff"], "0x08004258")
        self.assertEqual(keyed[4]["post_key_reads_portto"], "no")
        self.assertEqual(keyed[5]["post_key_reads_portto"], "no")

    def test_vertical_target_helper_has_three_recovered_callsites_and_discards_target_x(self):
        rows = mod.extract_player_vertical_target_calls(self.data)
        keyed = {row["callsite"]: row for row in rows}
        self.assertEqual(set(keyed), {"0x08002DD6", "0x080041C8", "0x080042BE"})
        self.assertEqual(keyed["0x08002DD6"]["target_x_write"], "source actor X -> Player+0x390")
        self.assertEqual(keyed["0x08002DD6"]["target_y_write"], "source actor Y -> Player+0x394")
        self.assertEqual(keyed["0x080041C8"]["target_x_write"], "none in this call path")
        self.assertEqual(keyed["0x080041C8"]["target_y_write"], "512px -> Player+0x394")
        self.assertEqual(keyed["0x080042BE"]["target_x_write"], "826px -> Player+0x390")
        self.assertIn("360px or 410px", keyed["0x080042BE"]["target_y_write"])
        self.assertTrue(all(row["helper_consumes_target_x"] == "no" for row in rows))
        self.assertTrue(all(row["helper_clears_target_x"] == "yes" for row in rows))

    def test_interaction_action_table_recovers_four_root_submenus_and_sixteen_leaf_actions(self):
        self.assertTrue(hasattr(mod, "extract_player_interaction_action_table"), "missing interaction action-table extractor")
        rows = mod.extract_player_interaction_action_table(self.data)
        self.assertEqual(len(rows), 20)
        self.assertEqual([row["label"] for row in rows[:4]], ["TALK", "FLIRT", "ASSAULT", "SHARE"])
        self.assertEqual([row["node_type"] for row in rows[:4]], [0, 0, 0, 0])
        self.assertEqual([row["child_base"] for row in rows[:4]], [4, 8, 12, 16])
        self.assertEqual(rows[0]["children"], "SUBJECT|Ask about|JOKE|CRITICIZE")
        self.assertEqual(rows[1]["children"], "KISS CHEEK|KISS LIPS|DIRTY JOKE|BREAKUP")
        self.assertEqual(rows[2]["children"], "SWEAR|FIGHT|unused|SCAM")
        self.assertEqual(rows[3]["children"], "GIFT|ACTIVITY|A Number|ASK")
        self.assertTrue(all(row["node_type"] == 1 for row in rows[4:]))
        self.assertTrue(all(row["child_base"] == "" for row in rows[4:]))
        self.assertEqual(rows[0]["source_rom_addr"], "0x08018738")
        self.assertEqual(rows[-1]["source_rom_addr"], "0x08018A7C")
        self.assertTrue(all(row["record_size"] == 44 for row in rows))

    def test_interaction_secondary_topic_table_maps_only_counted_leaf_actions(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_secondary_topics"),
            "missing interaction secondary-topic extractor",
        )
        rows = mod.extract_player_interaction_secondary_topics(self.data)
        keyed = {row["action_label"]: row for row in rows}
        self.assertEqual(set(keyed), {"SUBJECT", "Ask about", "CRITICIZE"})
        self.assertEqual(keyed["SUBJECT"]["topic_start"], 0)
        self.assertEqual(keyed["SUBJECT"]["topic_count"], 9)
        self.assertEqual(
            keyed["SUBJECT"]["topics"],
            "sports|movies|fashion|video games|school|future|parties|last event|mysteries",
        )
        self.assertEqual(keyed["Ask about"]["topic_start"], 10)
        self.assertEqual(keyed["Ask about"]["topic_count"], 5)
        self.assertEqual(
            keyed["Ask about"]["topics"],
            "hobbies|fav. music|best places|fav. meals|dreams",
        )
        self.assertEqual(keyed["CRITICIZE"]["topics"], keyed["SUBJECT"]["topics"])
        for row in rows:
            self.assertEqual(row["builder"], "0x08006E00")
            self.assertEqual(row["topic_table"], "0x080114B4")
            self.assertEqual(row["topic_stride"], 15)
            self.assertEqual(row["field_24_role"], "topic_start when field_28 > 0")
            self.assertEqual(row["field_28_role"], "topic_count")
            self.assertEqual(row["confidence"], "high")

    def test_interaction_subject_and_criticize_response_banks_are_topic_indexed(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_topic_response_banks"),
            "missing interaction topic-response-bank extractor",
        )
        rows = mod.extract_player_interaction_topic_response_banks(self.data)
        self.assertEqual(len(rows), 9)
        keyed = {row["topic_index"]: row for row in rows}
        self.assertEqual(keyed[0]["topic"], "sports")
        self.assertEqual(keyed[0]["subject_response_base"], "0x08018078")
        self.assertEqual(keyed[0]["criticize_response_base"], "0x08014DD8")
        self.assertEqual(keyed[6]["topic"], "parties")
        self.assertEqual(keyed[7]["topic"], "last event")
        self.assertEqual(keyed[8]["topic"], "mysteries")
        self.assertEqual(keyed[7]["subject_response_base"], keyed[8]["subject_response_base"] )
        self.assertEqual(keyed[7]["criticize_response_base"], keyed[8]["criticize_response_base"] )
        for row in rows:
            self.assertEqual(row["profile_table"], "0x0300110C")
            self.assertEqual(row["profile_topic_value_offset"], "+4*(topic_index+6)")
            self.assertEqual(row["subject_pointer_table"], "0x030007D4")
            self.assertEqual(row["criticize_pointer_table"], "0x030007AC")
            self.assertEqual(row["subject_variants_per_topic"], 16)
            self.assertEqual(row["criticize_variants_per_topic"], 8)
            self.assertEqual(row["response_stride"], 108)
            self.assertEqual(row["neutral_response"], "I don't really care")
            self.assertEqual(
                row["profile_value_dispatch"],
                "0..4 select response classes; other values fall through the generic interaction path",
            )
            self.assertEqual(row["subject_profile_value_0_slots"], "0|4|8|12")
            self.assertEqual(row["subject_profile_value_4_slots"], "3|7|11|15")
            self.assertEqual(row["criticize_profile_value_0_slots"], "0|4")
            self.assertEqual(row["criticize_profile_value_4_slots"], "3|7")
            self.assertEqual(row["confidence"], "high")

    def test_interaction_topic_response_text_export_preserves_all_subject_and_criticize_slots(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_topic_response_texts"),
            "missing interaction topic-response-text extractor",
        )
        rows = mod.extract_player_interaction_topic_response_texts(self.data)
        self.assertEqual(len(rows), 216)
        self.assertEqual(rows[0]["action"], "SUBJECT")
        self.assertEqual(rows[0]["topic"], "sports")
        self.assertEqual(rows[0]["slot"], 0)
        self.assertEqual(rows[0]["profile_value_class"], 0)
        self.assertEqual(rows[0]["variant"], 0)
        self.assertEqual(rows[0]["rom_addr"], "0x08018078")
        self.assertEqual(
            rows[0]["text"],
            "These jocks are just pricks. Why you even bother me with that?",
        )
        criticize0 = next(
            row for row in rows
            if row["action"] == "CRITICIZE" and row["topic_index"] == 0 and row["slot"] == 0
        )
        self.assertEqual(criticize0["profile_value_class"], 0)
        self.assertEqual(criticize0["variant"], 0)
        self.assertEqual(criticize0["rom_addr"], "0x08014DD8")
        self.assertEqual(
            criticize0["text"],
            "Yeah, that's what I always told - if you love sports, you got issues, bro!",
        )
        self.assertTrue(all(row["response_stride"] == 108 for row in rows))
        self.assertTrue(all(row["confidence"] == "high" for row in rows))

    def test_interaction_state2_cursor_starts_zero_and_moves_on_fresh_up_down(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_state2_cursor"),
            "missing interaction state-2 cursor extractor",
        )
        row = mod.extract_player_interaction_state2_cursor(self.data)
        self.assertEqual(row["cursor_offset"], "+0x1F0")
        self.assertEqual(row["entry_value"], 0)
        self.assertEqual(row["entry_handler"], "0x08009DDA")
        self.assertEqual(row["up_handler"], "0x08008C16")
        self.assertEqual(row["up_behavior"], "fresh Up decrements cursor when cursor > 0")
        self.assertEqual(row["down_handler"], "0x080099F8")
        self.assertEqual(row["down_behavior"], "fresh Down increments cursor when cursor <= 7")
        self.assertEqual(row["mechanical_range"], "0..8")
        self.assertEqual(row["rebuild_calls"], "0x080074D8|0x08006E00")
        self.assertEqual(row["per_action_count_clamp"], "not proved; movement code uses global 0..8 bound")
        self.assertEqual(row["confidence"], "high")

    def test_interaction_runtime_response_dispatch_is_quadrant_only(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_runtime_dispatch"),
            "missing interaction runtime-dispatch extractor",
        )
        rows = mod.extract_player_interaction_runtime_dispatch(self.data)
        self.assertEqual(len(rows), 16)
        keyed = {row["action_label"]: row for row in rows}
        self.assertEqual(keyed["SUBJECT"]["runtime_path"], "SUBJECT response bank")
        self.assertEqual(keyed["Ask about"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["JOKE"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["CRITICIZE"]["runtime_path"], "CRITICIZE response bank")
        self.assertEqual(keyed["KISS CHEEK"]["runtime_path"], "SUBJECT response bank")
        self.assertEqual(keyed["KISS LIPS"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["DIRTY JOKE"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["BREAKUP"]["runtime_path"], "CRITICIZE response bank")
        self.assertEqual(keyed["SWEAR"]["runtime_path"], "SUBJECT response bank")
        self.assertEqual(keyed["FIGHT"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["SCAM"]["runtime_path"], "CRITICIZE response bank")
        self.assertEqual(keyed["GIFT"]["runtime_path"], "SUBJECT response bank")
        self.assertEqual(keyed["ACTIVITY"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["A Number"]["runtime_path"], "set Player+0x382=1")
        self.assertEqual(keyed["ASK"]["runtime_path"], "CRITICIZE response bank")
        self.assertTrue(all(row["dispatcher"] == "0x08009200" for row in rows))
        self.assertTrue(all(row["dispatch_key"] == "Player+0x1E4 quadrant only" for row in rows))
        self.assertTrue(all(row["page_base_consulted"] == "no" for row in rows))
        self.assertTrue(all(row["confidence"] == "high" for row in rows))

    def test_interaction_shared_quadrant_followup_flag_has_fresh_a_handshake(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_followup_handshake"),
            "missing interaction follow-up handshake extractor",
        )
        row = mod.extract_player_interaction_followup_handshake(self.data)
        self.assertEqual(row["armed_by"], "quadrants 1 and 2 at 0x08009212")
        self.assertEqual(row["flag_offset"], "+0x382")
        self.assertEqual(row["consumer"], "0x0800852E")
        self.assertEqual(row["trigger"], "fresh A while Player+0x382 != 0")
        self.assertEqual(row["clears"], "Player+0x382|Player+0x381|Player+0x1EC")
        self.assertEqual(row["active_global_write"], "0x03000610=1")
        self.assertEqual(row["result_state"], 0)
        self.assertEqual(row["confidence"], "high")

    def test_interaction_profile_selector_table_separates_real_social_profiles_from_wrong_layout_records(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_profile_selector_table"),
            "missing interaction profile-selector extractor",
        )
        rows = mod.extract_player_interaction_profile_selector_table(self.data)
        keyed = {row["selector_index"]: row for row in rows}
        self.assertEqual(sorted(keyed), list(range(9)))
        self.assertEqual(keyed[0]["name"], "Stas")
        self.assertEqual(keyed[0]["record_kind"], "social_profile_0x3C")
        self.assertEqual(keyed[0]["profile_ptr"], "0x030010D0")
        self.assertEqual(keyed[1]["name"], "Julia")
        self.assertEqual(keyed[1]["record_kind"], "social_profile_0x3C")
        self.assertEqual(keyed[1]["profile_ptr"], "0x03001094")
        self.assertEqual(keyed[2]["profile_ptr"], "0x00000000")
        self.assertEqual(keyed[2]["record_kind"], "null")
        self.assertEqual([keyed[i]["name"] for i in range(3, 9)],
                         ["Stas", "IQ 54", "Kate", "Kiata", "Alex", "Evelina"])
        self.assertTrue(all(keyed[i]["record_kind"] == "npc_metadata_0x30_wrong_for_social_code"
                            for i in range(3, 9)))

    def test_interaction_real_social_profiles_recover_all_nine_numeric_topic_classes(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_social_profile_topics"),
            "missing social-profile topic extractor",
        )
        rows = mod.extract_player_interaction_social_profile_topics(self.data)
        by_name = {}
        for row in rows:
            by_name.setdefault(row["name"], []).append(row)
        self.assertEqual([r["rating"] for r in by_name["Stas"]], [3, 4, 0, 2, 1, 1, 3, 2, 2])
        self.assertEqual([r["rating"] for r in by_name["Julia"]], [1, 2, 2, 0, 1, 2, 4, 2, 3])
        self.assertTrue(all(0 <= r["rating"] <= 4 for r in rows))
        self.assertTrue(all(r["profile_field_14_initial"] == 0 for r in rows))

    def test_interaction_profile_field14_has_centered_topic_score_update(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_social_score_semantics"),
            "missing social-score semantics extractor",
        )
        row = mod.extract_player_interaction_social_score_semantics(self.data)
        self.assertEqual(row["profile_field"], "+0x14")
        self.assertEqual(row["update_formula"], "profile+0x14 += 2 * (topic_class - 2)")
        self.assertEqual(row["topic_class_deltas"], "0:-4|1:-2|2:0|3:+2|4:+4")
        self.assertEqual(row["player_follower_offset"], "+0x39C")
        self.assertEqual(row["player_follower_target"], "10 * profile+0x14")
        self.assertEqual(row["semantic_name"], "relationship-like social score")
        self.assertEqual(row["proper_profile_initial_values"], "Stas:0|Julia:0")
        self.assertEqual(row["name_confidence"], "medium-high")
        self.assertEqual(row["behavior_confidence"], "high")

    def test_interaction_wrong_layout_profile_entries_overlap_topic_class_reads(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_profile_topic_layout_mismatch"),
            "missing profile/topic-layout mismatch extractor",
        )
        rows = mod.extract_player_interaction_profile_topic_layout_mismatch(self.data)
        self.assertEqual(len(rows), 54)
        self.assertEqual(sum(r["valid_response_class"] == "yes" for r in rows), 23)
        stas = [r for r in rows if r["selector_index"] == 3]
        evelina = [r for r in rows if r["selector_index"] == 8]
        self.assertEqual(stas[0]["raw_value"], 0)
        self.assertEqual(stas[0]["valid_response_class"], "yes")
        self.assertEqual(stas[1]["raw_value_hex"], "0x7473754A")
        self.assertEqual(stas[1]["ascii_le"], "Just")
        self.assertEqual(stas[1]["valid_response_class"], "no")
        self.assertEqual(evelina[0]["raw_value"], 7)
        self.assertEqual(evelina[0]["valid_response_class"], "no")
        self.assertTrue(any(r["ascii_le"] == "Popu" for r in evelina))
        self.assertTrue(all(r["behavior_confidence"] == "high" for r in rows))

    def test_interaction_profile_selector_integrity_exposes_demo_layout_hazard(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_profile_selector_integrity"),
            "missing interaction profile-selector integrity extractor",
        )
        row = mod.extract_player_interaction_profile_selector_integrity(self.data)
        self.assertEqual(row["proper_social_profiles"], 2)
        self.assertEqual(row["null_entries"], 1)
        self.assertEqual(row["wrong_layout_entries"], 6)
        self.assertEqual(row["wrong_layout_topic_reads"], 54)
        self.assertEqual(row["wrong_layout_reads_in_0_4"], 23)
        self.assertEqual(row["runtime_profile_deref"], "0x0800948C")
        self.assertEqual(row["selector_null_guard"], "none before profile/topic dereference")
        self.assertEqual(row["null_selector_index"], 2)
        self.assertEqual(row["actor_selector_source"], "actor+0x5C -> Player+0x388")
        self.assertEqual(row["parity_warning"], "do not normalize selector table in faithful demo mode")
        self.assertEqual(row["behavior_confidence"], "high")

    def test_interaction_followup_moves_player_39c_toward_profile_field14_times_ten(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_profile_target_step"),
            "missing profile-linked interaction target-step extractor",
        )
        row = mod.extract_player_interaction_profile_target_step(self.data)
        self.assertEqual(row["player_offset"], "+0x39C")
        self.assertEqual(row["profile_selector_offset"], "+0x388")
        self.assertEqual(row["profile_table"], "0x0300110C")
        self.assertEqual(row["profile_field_offset"], "+0x14")
        self.assertEqual(row["target_formula"], "10 * profile[+0x14]")
        self.assertEqual(row["below_target"], "increment Player+0x39C by 1")
        self.assertEqual(row["above_target"], "decrement Player+0x39C by 1")
        self.assertEqual(row["at_target"], "leave Player+0x39C unchanged")
        self.assertEqual(row["semantic_name"], "scaled relationship-like score mirror/follower")
        self.assertEqual(row["confidence"], "high")

    def test_interaction_profile_field14_directly_synchronizes_player_39c_at_ten_x(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_score_mirror_semantics"),
            "missing interaction score-mirror extractor",
        )
        row = mod.extract_player_interaction_score_mirror_semantics(self.data)
        self.assertEqual(row["direct_sync_site"], "0x080090F8")
        self.assertEqual(row["profile_field"], "+0x14")
        self.assertEqual(row["player_field"], "+0x39C")
        self.assertEqual(row["direct_sync_formula"], "Player+0x39C = 10 * profile+0x14")
        self.assertEqual(row["position"], "before quadrant-specific response branch")
        self.assertEqual(row["working_name"], "scaled relationship-like score mirror/follower")
        self.assertEqual(row["behavior_confidence"], "high")

    def test_interaction_depth_counter_and_talk_only_state2_a_exit_are_proved(self):
        self.assertTrue(
            hasattr(mod, "extract_player_interaction_depth_semantics"),
            "missing interaction depth-semantics extractor",
        )
        row = mod.extract_player_interaction_depth_semantics(self.data)
        self.assertEqual(row["depth_offset"], "+0x38C")
        self.assertEqual(row["submenu_confirm"], "increments depth at 0x08009C62")
        self.assertEqual(row["leaf_entry"], "reloads depth at 0x08009E18 then increments through 0x08009C62")
        self.assertEqual(row["b_return"], "decrements depth at 0x08008C98")
        self.assertEqual(row["state2_fresh_a_gate"], "depth > 0 and page_base == 4 -> state 3")
        self.assertEqual(row["talk_page_base"], 4)
        self.assertEqual(row["other_page_bases"], "8|12|16")
        self.assertEqual(row["other_page_fresh_a"], "exits Player_update path without changing interaction state")
        self.assertEqual(row["confidence"], "high")

    def test_player_interaction_state_machine_recovers_selector_leaf_and_teardown_transitions(self):
        self.assertTrue(hasattr(mod, "extract_player_interaction_state_transitions"), "missing interaction state-transition extractor")
        rows = mod.extract_player_interaction_state_transitions(self.data)
        keyed = {row["transition"]: row for row in rows}
        self.assertEqual(keyed["alignment_to_selector"]["from_state"], 0)
        self.assertEqual(keyed["alignment_to_selector"]["to_state"], 1)
        self.assertIn("four", keyed["alignment_to_selector"]["proven_behavior"])
        self.assertEqual(keyed["selector_up"]["choice"], 0)
        self.assertEqual(keyed["selector_right"]["choice"], 1)
        self.assertEqual(keyed["selector_down"]["choice"], 2)
        self.assertEqual(keyed["selector_left"]["choice"], 3)
        self.assertEqual(keyed["selector_branch_confirm"]["condition"], "selected record +0x20 == 0")
        self.assertEqual(keyed["selector_branch_confirm"]["to_state"], 0)
        self.assertIn("+0x24", keyed["selector_branch_confirm"]["proven_behavior"])
        self.assertEqual(keyed["selector_leaf_confirm"]["condition"], "selected record +0x20 == 1")
        self.assertEqual(keyed["selector_leaf_confirm"]["to_state"], 2)
        self.assertEqual(keyed["secondary_b_return"]["from_state"], 2)
        self.assertEqual(keyed["secondary_b_return"]["to_state"], 0)
        self.assertEqual(keyed["teardown"]["from_state"], 3)
        self.assertEqual(keyed["teardown"]["to_state"], 0)
        self.assertIn("0x03000610=0", keyed["teardown"]["proven_behavior"])

    def test_npc_interaction_alignment_bootstrap_uses_full_xy_anchors(self):
        self.assertTrue(hasattr(mod, "extract_player_npc_interaction_alignment"), "missing NPC interaction alignment extractor")
        rows = mod.extract_player_npc_interaction_alignment(self.data)
        keyed = {row["side"]: row for row in rows}
        self.assertEqual(set(keyed), {"anchor_at_or_right", "anchor_left"})
        for row in rows:
            self.assertEqual(row["source_handler"], "0x08002FCE")
            self.assertEqual(row["trigger"], "fresh A press while interaction-active flag is clear")
            self.assertEqual(row["dialogue_index_write"], "actor+0x5C -> Player+0x388")
            self.assertEqual(row["anchor_x_write"], "actor+0x08 -> Player+0x390")
            self.assertEqual(row["anchor_y_write"], "actor+0x0C -> Player+0x394")
            self.assertEqual(row["interaction_active_global"], "0x03000610=1")
            self.assertEqual(row["player_update_dispatch"], "0x08008BC8")
            self.assertEqual(row["interaction_state_offset"], "+0x1EC")
            self.assertEqual(row["required_state"], 0)
            self.assertEqual(row["alignment_entry"], "0x0800921A")
            self.assertEqual(row["vertical_formula"], "Player+0x1C=anchorY-currentY")
            self.assertEqual(row["collision_motion_solver"], "0x08004670")
            self.assertEqual(row["next_state"], 1)
            self.assertEqual(row["normal_path_anchor_reset"], "Player+0x390=1; Player+0x394=1 at 0x0800842A")
        self.assertEqual(keyed["anchor_at_or_right"]["horizontal_formula"], "Player+0x18=anchorX-currentX-0x1300")
        self.assertEqual(keyed["anchor_at_or_right"]["intended_horizontal_separation_px"], -19)
        self.assertEqual(keyed["anchor_at_or_right"]["facing_value"], 1)
        self.assertEqual(keyed["anchor_left"]["horizontal_formula"], "Player+0x18=anchorX-currentX+0x1300")
        self.assertEqual(keyed["anchor_left"]["intended_horizontal_separation_px"], 19)
        self.assertEqual(keyed["anchor_left"]["facing_value"], 0)

    def test_player_interaction_symbols_include_update_motion_solver_and_active_flag(self):
        funcs = {addr: (name, evidence) for addr, name, evidence in struct_mod.KNOWN_FUNCTIONS}
        globs = {addr: (name, evidence) for addr, name, evidence in struct_mod.KNOWN_GLOBALS}
        self.assertIn(0x080081B0, funcs)
        self.assertIn(0x08004670, funcs)
        self.assertIn(0x03000610, globs)
        self.assertEqual(funcs[0x080081B0][0], "Player_update")
        self.assertEqual(funcs[0x08004670][0], "apply_actor_motion_with_tile_collision_candidate")
        self.assertIn("+0x18/+0x1C", funcs[0x08004670][1])
        self.assertEqual(globs[0x03000610][0], "player_interaction_active_flag")
        self.assertIn("0x08002FF2", globs[0x03000610][1])

    def test_ending_vram_effect_exports_exact_copy_length_equations(self):
        rows = mod.extract_ending_vram_effect_copy_model(self.data)
        keyed = {row["destination"]: row for row in rows}
        self.assertEqual(keyed["0x06000000"]["bytes_per_step"], 1500)
        self.assertEqual(keyed["0x06000000"]["argument_bias"], 64)
        self.assertEqual(keyed["0x06000000"]["size_at_argument_0"], 96000)
        self.assertEqual(keyed["0x06000000"]["size_formula"], "1500*(argument+64)")
        self.assertEqual(keyed["0x06010000"]["bytes_per_step"], 250)
        self.assertEqual(keyed["0x06010000"]["size_at_argument_0"], 16000)
        self.assertEqual(keyed["0x06010000"]["size_formula"], "250*(argument+64)")
        self.assertEqual(keyed["0x06000000"]["copy_helper"], "0x08010C54")

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
        self.assertEqual(funcs[0x080080A4][0], "Player_apply_vertical_target_delta")
        self.assertIn("+0x394", funcs[0x080080A4][1])
        self.assertEqual(globs[0x0300061C][0], "state4_monster_render_flag")
        self.assertEqual(globs[0x03000620][0], "state4_collection_progress_index")
        self.assertIn("normal-context", globs[0x030006AC][1])


if __name__ == '__main__':
    unittest.main()
