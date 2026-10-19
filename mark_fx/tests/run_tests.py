#!/usr/bin/env python3
"""
Mark FX Automated Test Runner
Executes all 4 tiers of automated opaque-box test suites for the Mark FX Laser Tag system.

Usage:
    python3 mark_fx/tests/run_tests.py
    python3 mark_fx/tests/run_tests.py --verbose
    python3 mark_fx/tests/run_tests.py --tier 1
    python3 mark_fx/tests/run_tests.py --module test_electrical_safety
"""

import sys
import os
import time
import argparse
import unittest
from typing import List, Dict, Any, Optional

# Ensure project root is on sys.path
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# List of all test modules with tier associations and descriptions
TEST_REGISTRY = [
    {
        "module": "mark_fx.tests.test_electrical_safety",
        "name": "Electrical & Circuit Safety",
        "file": "test_electrical_safety.py",
        "tiers": [1, 2],
        "description": "IR LED 100Ω–110Ω 15–20mA, HUD LEDs <25mA, TSOP <5mA, Umbilical, Banned Components",
    },
    {
        "module": "mark_fx.tests.test_nec_protocol",
        "name": "8-Player NEC IR Protocol",
        "file": "test_nec_protocol.py",
        "tiers": [1, 2],
        "description": "32-bit NEC bitwise inverse validation, P1..P8 codes, orthogonality, server serialization",
    },
    {
        "module": "mark_fx.tests.test_hud_audio_engine",
        "name": "5-LED HUD & Sound Engine",
        "file": "test_hud_audio_engine.py",
        "tiers": [1, 2],
        "description": "5-LED states (5..0, shield, flash, sweep), 10 polyphonic melodies, audio/visual sync",
    },
    {
        "module": "mark_fx.tests.test_trigger_timing",
        "name": "Trigger Debounce & Rate Limiter",
        "file": "test_trigger_timing.py",
        "tiers": [1, 2],
        "description": "40ms software debounce, 600ms rate limiter lockout, edge detection, continuous hold suppression",
    },
    {
        "module": "mark_fx.tests.test_server_protocol",
        "name": "Server Protocol & Referee Rules",
        "file": "test_server_protocol.py",
        "tiers": [1, 2],
        "description": "UDP 5051 discovery, /heartbeat, /hit, friendly fire medic heal, traitor defection, scoring",
    },
    {
        "module": "mark_fx.tests.test_standalone_mode",
        "name": "Autonomous Standalone Fallback",
        "file": "test_standalone_mode.py",
        "tiers": [1, 2],
        "description": "Offline internal referee, damage progression, 10s respawn, 3s shield, zero-wifi resilience",
    },
    {
        "module": "mark_fx.tests.test_cross_feature_matrix",
        "name": "Cross-Feature Matrix",
        "file": "test_cross_feature_matrix.py",
        "tiers": [3],
        "description": "Pairwise interactions: trigger during audio, hit while firing, shield blocking during flash",
    },
    {
        "module": "mark_fx.tests.test_real_world_scenarios",
        "name": "Real-World Match Scenarios",
        "file": "test_real_world_scenarios.py",
        "tiers": [4],
        "description": "Full match simulations: 4v4 progression, medic traitor conversion, sudden death, offline skirmish",
    },
]


def parse_args():
    parser = argparse.ArgumentParser(description="Mark FX Automated Test Runner")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose test execution output")
    parser.add_argument("--tier", type=int, choices=[1, 2, 3, 4], help="Run only tests from a specific tier (1, 2, 3, or 4)")
    parser.add_argument("--module", type=str, help="Run only a specific test module (e.g. test_electrical_safety)")
    parser.add_argument("--list", action="store_true", help="List all registered test modules and exit")
    return parser.parse_args()


def filter_test_classes(suite: unittest.TestSuite, target_tier: Optional[int]) -> unittest.TestSuite:
    """Filter test cases in suite by Tier if target_tier is specified."""
    if target_tier is None:
        return suite

    filtered_suite = unittest.TestSuite()
    tier_tag = f"Tier{target_tier}"
    
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            sub = filter_test_classes(item, target_tier)
            if sub.countTestCases() > 0:
                filtered_suite.addTest(sub)
        elif isinstance(item, unittest.TestCase):
            cls_name = item.__class__.__name__
            if tier_tag in cls_name:
                filtered_suite.addTest(item)
    return filtered_suite


def run():
    args = parse_args()

    if args.list:
        print("\n=== MARK FX REGISTERED TEST MODULES ===")
        for entry in TEST_REGISTRY:
            print(f" • {entry['file']:<30} | Tiers: {entry['tiers']} | {entry['name']}")
            print(f"   Description: {entry['description']}\n")
        sys.exit(0)

    print("\n" + "=" * 78)
    print("      MARK FX ESP32 LASER TAG SYSTEM — 4-TIER AUTOMATED TEST RUNNER")
    print("=" * 78)
    if args.tier:
        print(f" Filter: Running only Tier {args.tier} tests")
    if args.module:
        print(f" Filter: Running only module '{args.module}'")
    print("-" * 78)

    loader = unittest.TestLoader()
    total_tests = 0
    total_passed = 0
    total_failed = 0
    total_errors = 0
    module_results: List[Dict[str, Any]] = []

    start_total_time = time.perf_counter()

    for entry in TEST_REGISTRY:
        if args.module and args.module not in entry["file"] and args.module not in entry["module"]:
            continue
        if args.tier and args.tier not in entry["tiers"]:
            continue

        module_name = entry["module"]
        try:
            mod_suite = loader.loadTestsFromName(module_name)
        except Exception as e:
            print(f"[ERROR] Could not load module {module_name}: {e}")
            total_errors += 1
            continue

        if args.tier:
            mod_suite = filter_test_classes(mod_suite, args.tier)

        test_count = mod_suite.countTestCases()
        if test_count == 0:
            continue

        # Run this suite
        stream = sys.stdout if args.verbose else open(os.devnull, "w")
        runner = unittest.TextTestRunner(stream=stream, verbosity=2 if args.verbose else 0)
        
        start_mod_time = time.perf_counter()
        result = runner.run(mod_suite)
        elapsed_mod_time = time.perf_counter() - start_mod_time

        passed = test_count - len(result.failures) - len(result.errors)
        failed = len(result.failures)
        errors = len(result.errors)

        total_tests += test_count
        total_passed += passed
        total_failed += failed
        total_errors += errors

        status_str = "PASS" if (failed == 0 and errors == 0) else "FAIL"
        module_results.append({
            "name": entry["name"],
            "file": entry["file"],
            "count": test_count,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "time": elapsed_mod_time,
            "status": status_str,
            "failures": result.failures,
            "err_list": result.errors,
        })

    total_duration = time.perf_counter() - start_total_time

    # Print summary table
    print(f"{'Module File':<32} {'Tests':<7} {'Pass':<6} {'Fail':<6} {'Time':<8} {'Status':<6}")
    print("-" * 78)
    for res in module_results:
        print(f"{res['file']:<32} {res['count']:<7} {res['passed']:<6} {res['failed']:<6} {res['time']:<7.3f}s {res['status']:<6}")
    print("=" * 78)

    # Detailed failures if any
    if total_failed > 0 or total_errors > 0:
        print("\nFAILURE DETAILS:")
        for res in module_results:
            for test_case, tb in res["failures"]:
                print(f"FAIL: {test_case}")
                print(tb)
            for test_case, tb in res["err_list"]:
                print(f"ERROR: {test_case}")
                print(tb)

    print(f"\nRESULTS: {total_tests} Tests Ran in {total_duration:.3f}s")
    print(f"PASSED : {total_passed}")
    print(f"FAILED : {total_failed}")
    print(f"ERRORS : {total_errors}")

    if total_failed == 0 and total_errors == 0 and total_tests > 0:
        print("\n[SUCCESS] ALL MARK FX TEST SUITES PASSED WITH ZERO ERRORS!\n")
        sys.exit(0)
    else:
        print(f"\n[FAILURE] {total_failed + total_errors} TEST(S) FAILED!\n")
        sys.exit(1)


if __name__ == "__main__":
    run()
