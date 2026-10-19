"""
Mark FX Laser Tag - 8-Player NEC IR Protocol Verification Suite
Covers Requirement R5 and Acceptance Criteria AC-8.
Tier 1: Feature Coverage (>=5 test cases)
Tier 2: Boundary & Corner Cases (>=5 test cases)
"""

import os
import sys
import unittest

# Ensure repo root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mark_fx.tests.models import NECProtocol


class TestNECProtocolTier1(unittest.TestCase):
    """Tier 1: Feature Coverage for 8-Player NEC IR Protocol."""

    def test_all_8_players_defined(self):
        """Verify all 8 players P1 through P8 are defined with unique codes."""
        players = list(NECProtocol.PLAYER_CODES.keys())
        self.assertEqual(len(players), 8)
        self.assertEqual(players, ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"])

    def test_team_allocations_blue_vs_red(self):
        """Verify P1..P4 are FRIEND (Blue Team) and P5..P8 are ENEMY (Red Team)."""
        for p in ["P1", "P2", "P3", "P4"]:
            self.assertEqual(NECProtocol.PLAYER_CODES[p]["team"], "FRIEND")
        for p in ["P5", "P6", "P7", "P8"]:
            self.assertEqual(NECProtocol.PLAYER_CODES[p]["team"], "ENEMY")

    def test_bitwise_inverse_validation_all_8_players(self):
        """Verify 32-bit bitwise complement integrity for all 8 players."""
        for p_id, data in NECProtocol.PLAYER_CODES.items():
            code = data["code"]
            self.assertTrue(
                NECProtocol.validate_nec_integrity(code),
                f"Player {p_id} code 0x{code:08X} failed NEC bitwise complement check!"
            )

    def test_player_code_orthogonality(self):
        """Verify all 8 player codes are completely distinct with no duplicates."""
        codes = [data["code"] for data in NECProtocol.PLAYER_CODES.values()]
        self.assertEqual(len(codes), len(set(codes)), "Duplicate player IR codes detected!")

    def test_p1_friend1_code(self):
        """Verify P1 code matches server.py (0x00FF30CF, Friend 1)."""
        p1 = NECProtocol.PLAYER_CODES["P1"]
        self.assertEqual(p1["code"], 0x00FF30CF)
        self.assertEqual(p1["hex"], "0xFF30CF")
        addr, inv_addr, cmd, inv_cmd = NECProtocol.decompose(p1["code"])
        self.assertEqual(addr, 0x00)
        self.assertEqual(inv_addr, 0xFF)
        self.assertEqual(cmd, 0x30)
        self.assertEqual(inv_cmd, 0xCF)

    def test_p5_enemy1_code(self):
        """Verify P5 code matches server.py (0x00FF38C7, Enemy 1)."""
        p5 = NECProtocol.PLAYER_CODES["P5"]
        self.assertEqual(p5["code"], 0x00FF38C7)
        self.assertEqual(p5["hex"], "0xFF38C7")
        addr, inv_addr, cmd, inv_cmd = NECProtocol.decompose(p5["code"])
        self.assertEqual(addr, 0x00)
        self.assertEqual(inv_addr, 0xFF)
        self.assertEqual(cmd, 0x38)
        self.assertEqual(inv_cmd, 0xC7)

    def test_nec_encoding_helper(self):
        """Verify encode_nec produces valid 32-bit word matching player definitions."""
        encoded_p2 = NECProtocol.encode_nec(0x00, 0x18)
        self.assertEqual(encoded_p2, 0x00FF18E7)
        encoded_p6 = NECProtocol.encode_nec(0x00, 0x5A)
        self.assertEqual(encoded_p6, 0x00FF5AA5)

    def test_server_format_serialization(self):
        """Verify code serialization format matching server.py sprintf."""
        for p_id, data in NECProtocol.PLAYER_CODES.items():
            formatted = NECProtocol.format_code_for_server(data["code"])
            # In Python format f"0x{code:X}", 0x00FF30CF formats to "0xFF30CF"
            self.assertEqual(formatted, f"0x{data['code']:X}")


class TestNECProtocolTier2(unittest.TestCase):
    """Tier 2: Boundary & Corner Cases for NEC IR Codes."""

    def test_corrupted_address_inversion(self):
        """Verify rejection when address inverse byte is corrupted by 1 bit."""
        valid_code = 0x00FF30CF
        # Corrupt inv_addr: 0xFF -> 0xFE
        corrupted_code = valid_code ^ (1 << 16)
        self.assertFalse(NECProtocol.validate_nec_integrity(corrupted_code))

    def test_corrupted_command_inversion(self):
        """Verify rejection when command inverse byte is corrupted by 1 bit."""
        valid_code = 0x00FF30CF
        # Corrupt inv_cmd: 0xCF -> 0xCE
        corrupted_code = valid_code ^ 1
        self.assertFalse(NECProtocol.validate_nec_integrity(corrupted_code))

    def test_non_zero_address_foreign_remote(self):
        """Verify non-zero address (e.g. TV remote address 0x20) is recognized as foreign."""
        # Commercial Samsung/LG remote: Addr 0x20, ~Addr 0xDF, Cmd 0x10, ~Cmd 0xEF
        foreign_code = (0x20 << 24) | (0xDF << 16) | (0x10 << 8) | 0xEF
        # Valid NEC framing:
        self.assertTrue(NECProtocol.validate_nec_integrity(foreign_code))
        # But not in player code list:
        self.assertIsNone(NECProtocol.lookup_code(foreign_code))

    def test_unmapped_code_lookup(self):
        """Verify unmapped valid NEC code returns None."""
        unmapped_code = NECProtocol.encode_nec(0x00, 0x99)
        self.assertIsNone(NECProtocol.lookup_code(unmapped_code))

    def test_code_lookup_normalization_hex_strings(self):
        """Verify lookup works across multiple string representations."""
        variants = ["0xFF30CF", "0xff30cf", "0x00FF30CF", "0x00ff30cf", 0x00FF30CF]
        for v in variants:
            res = NECProtocol.lookup_code(v)
            self.assertIsNotNone(res, f"Failed lookup for variant: {v}")
            self.assertEqual(res["id"], "P1")

    def test_repeat_code_handling(self):
        """Verify NEC repeat code (0xFFFFFFFF) does not match any player."""
        repeat_code = 0xFFFFFFFF
        self.assertIsNone(NECProtocol.lookup_code(repeat_code))
        # Repeat code does not have valid complement structure:
        self.assertFalse(NECProtocol.validate_nec_integrity(repeat_code))


if __name__ == "__main__":
    unittest.main()
