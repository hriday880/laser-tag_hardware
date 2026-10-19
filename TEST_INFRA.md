# Mark FX Test Infrastructure Specification

## 1. Overview & Test Philosophy
The **Mark FX** automated test infrastructure is a comprehensive, opaque-box, specification-driven test suite designed to validate the production-ready 8-player ESP32 laser tag system against all requirements and acceptance criteria established in `ORIGINAL_REQUEST.md` and `PROJECT.md`.

To guarantee maximum reproducibility, speed, and continuous integration portability:
- **Zero External Dependencies**: Built entirely upon the Python standard library (`unittest`, `math`, `time`, `json`, `argparse`). Runs out-of-the-box on standard macOS, Linux, and Windows developer environments without requiring `pip install`.
- **Dual-Track Decoupled Execution**: Emulates hardware physics, timers, state machines, and protocols in software models (`mark_fx/tests/models.py`), enabling instantaneous sub-second execution (93 tests in <0.3s) without requiring physical benchtop hardware.
- **Authoritative Referee Validation**: Directly exercises the central referee engine (`server/server.py`) to guarantee 100% protocol fidelity.

---

## 2. Test Architecture & Directory Layout

```
/Users/admin/Documents/LaserTag-hardware/
├── TEST_INFRA.md                         # This architecture specification
├── TEST_READY.md                         # Test suite readiness and execution summary
├── server/
│   └── server.py                         # Authoritative Python referee server
└── mark_fx/
    ├── __init__.py
    └── tests/
        ├── __init__.py
        ├── run_tests.py                  # Master test runner CLI with pass/fail exit codes
        ├── models.py                     # Emulation models (Physics, NEC, HUD, Audio, Debounce, Referee)
        ├── test_electrical_safety.py     # Tier 1 & 2: Resistor calculations, LED/TSOP current limits
        ├── test_nec_protocol.py          # Tier 1 & 2: 8-player 32-bit NEC codes & bitwise complements
        ├── test_hud_audio_engine.py      # Tier 1 & 2: 5-LED HUD states, audio note scheduler, A/V sync
        ├── test_trigger_timing.py        # Tier 1 & 2: 40ms debounce, 600ms rate limiter, non-blocking timing
        ├── test_server_protocol.py       # Tier 1 & 2: UDP discovery, /heartbeat, /hit, medic, traitor
        ├── test_standalone_mode.py       # Tier 1 & 2: Offline referee, backyard skirmish, network loss
        ├── test_cross_feature_matrix.py  # Tier 3: Pairwise feature combinations and race conditions
        └── test_real_world_scenarios.py  # Tier 4: Full match simulations (4v4, traitor, sudden death)
```

---

## 3. 4-Tier Test Case Design Methodology

The test suite strictly follows the 4-Tier Test Case Design Methodology:

### Tier 1: Feature Coverage (45 Tests)
Validates primary behavior (happy path) for all 8 core features:
1. **IR Direct Drive**: 100Ω and 110Ω resistor network sizing yields 15.0mA–20.0mA forward current; thermal dissipation on 1/4W resistor has >6x safety margin.
2. **5-LED Unicolor HUD**: Correct pin outputs on D18, D19, D21, D22, D23 across 5 HP (solid), damage (4..2), critical (1 HP panic pulse), eliminated (0 HP off), respawn shield (unison flash), muzzle flash (momentary burst), and lobby sweep.
3. **Passive Piezo Buzzer Direct Drive**: Direct drive from GPIO 33, capacitive piezo behavior, zero DC leakage, no back-EMF, and zero transistor requirement.
4. **Tactile Trigger**: GPIO 13 `INPUT_PULLUP` sensing, 40ms software debounce, 600ms fire cooldown, edge detection, and non-blocking polling.
5. **8-Player 32-Bit NEC IR Codes**: Orthogonal codes for P1 through P8, valid 32-bit word format, team assignments (Blue FRIEND P1..P4 vs Red ENEMY P5..P8).
6. **Vest 360° Array & Umbilical**: 5 TSOP1838 sensors in parallel drawing <5mA, 3-wire umbilical cable drop <5mV, D15 MTDO boot strapping pin compatibility.
7. **WiFi Auto-Discovery & Server Sync**: UDP 5051 `"LASERTAG 5050"` parsing, `/heartbeat` telemetry, `/hit` reporting, and device state synchronization.
8. **Autonomous Standalone Fallback**: Offline internal referee, local damage tracking (5..0), lives (3..0), 10s respawn, and 3s invulnerability shield.

### Tier 2: Boundary & Corner Cases (35 Tests)
Stresses the system at extreme limits, thresholds, and invalid states:
1. **Current Limits**: IR LED current strictly clamped between 15.0mA min (optical range) and 20.0mA max across component tolerances and supply fluctuations (3.0V–3.6V). Total HUD current strictly < 25.0mA.
2. **Debounce Cutoff**: 39ms contact bounce is rejected; 41ms press is accepted. Rapid burst clicks (10 in 300ms) are suppressed to 1 shot. Continuous trigger hold does not auto-fire.
3. **Health & Lives Clamping**: HP clamped at upper bound (5) and lower bound (0); lives cannot go negative.
4. **Corrupted IR Codes**: Single bitflip in address inverse or command inverse fails validation; non-zero commercial remote addresses and repeat codes (0xFFFFFFFF) are safely ignored.
5. **Phase & State Rejection**: Hits received during LOBBY, PAUSED, COUNTDOWN, RESPAWN, or OUT phases are rejected (`NOTLIVE` / `NOTALIVE`).
6. **Friendly Fire Traitor Escalation**: Medic cooldown violation accumulates strikes (1 -> 2 -> 3), causing defection to `TRAITOR` with subsequent damage infliction.
7. **Audio Priority Preemption**: Death knell (P3) preempts shot chirps (P1); low-priority sounds cannot interrupt high-priority melodies.

### Tier 3: Cross-Feature Combinations (8 Tests)
Exhaustive pairwise coverage of concurrent feature interactions:
- **Trigger during Audio Playback**: Pulling trigger while a melody is playing triggers muzzle flash and shot without audio lockup or CPU delay.
- **Hit Taken while Firing**: Outgoing shot transmission and incoming damage application execute concurrently without state collision.
- **Respawn Shield Blocking Hits during Audio**: Incoming enemy hits during shield return `BLOCKED` without disrupting shield melody or flashing HUD.
- **Server Disconnect Mid-Game**: Sudden loss of WiFi causes seamless handover to `StandaloneReferee`, preserving current HP, lives, and match time.
- **1 HP Panic Pulse during Muzzle Flash**: Muzzle flash overrides HUD for 50ms, then HUD immediately returns to 1 HP rapid panic pulse.
- **Medic Heal during Enemy Hit Cooldown**: Friendly medic heal is processed independently without getting blocked by enemy damage cooldown.
- **Trigger Locked Out during Respawn**: Pulling trigger while dead / respawning is rejected; weapon cannot fire until respawn completes.
- **Server Re-Discovery**: Standalone device receives UDP broadcast and re-attaches to server without resetting game state.

### Tier 4: Real-World Application Scenarios (5 Tests)
End-to-end match lifecycle simulations:
- **Scenario 1: 4v4 Match Progression**: Full match from LOBBY through COUNTDOWN, First Blood (+25 pts), multiple kills, 10s respawns, 3s shields, finisher bonus (+100 pts), and final scoreboard MVP attribution.
- **Scenario 2: Medic Friendly Fire & Traitor Conversion**: Friend heals player, then repeatedly shoots during cooldown until 3 strikes trigger traitor conversion; traitor then deals real damage.
- **Scenario 3: Sudden Death Match**: Match configured to 1 Life, 1 HP; single shot triggers immediate elimination, gameover, and finisher bonus.
- **Scenario 4: Offline Backyard Skirmish**: Device boots with zero WiFi; complete 3-life game is played using autonomous referee and HUD feedback.
- **Scenario 5: Network Glitch & Auto-Recovery**: 30-second WiFi outage mid-game; device maintains state locally, re-attaches, and resyncs with server.

---

## 4. Test Runner CLI Usage

The master test runner is located at `mark_fx/tests/run_tests.py`.

### Execution Commands

```bash
# Run the entire test suite (93 tests)
python3 mark_fx/tests/run_tests.py

# Run with verbose output showing individual test names
python3 mark_fx/tests/run_tests.py --verbose

# Run a specific tier (1, 2, 3, or 4)
python3 mark_fx/tests/run_tests.py --tier 1
python3 mark_fx/tests/run_tests.py --tier 2
python3 mark_fx/tests/run_tests.py --tier 3
python3 mark_fx/tests/run_tests.py --tier 4

# Run a specific module
python3 mark_fx/tests/run_tests.py --module test_electrical_safety
python3 mark_fx/tests/run_tests.py --module test_nec_protocol
python3 mark_fx/tests/run_tests.py --module test_server_protocol

# List all registered test modules
python3 mark_fx/tests/run_tests.py --list
```

### Exit Codes
- `0`: All tests passed successfully.
- `1`: One or more tests failed or encountered errors.

---

## 5. Test Suite Verification Summary

| Suite Module | Tiers Covered | Test Count | Pass Rate | Execution Time |
|---|---|---|---|---|
| `test_electrical_safety.py` | Tier 1, Tier 2 | 16 | 100% | 0.002s |
| `test_nec_protocol.py` | Tier 1, Tier 2 | 14 | 100% | 0.003s |
| `test_hud_audio_engine.py` | Tier 1, Tier 2 | 16 | 100% | 0.003s |
| `test_trigger_timing.py` | Tier 1, Tier 2 | 10 | 100% | 0.003s |
| `test_server_protocol.py` | Tier 1, Tier 2 | 13 | 100% | 0.020s |
| `test_standalone_mode.py` | Tier 1, Tier 2 | 11 | 100% | 0.001s |
| `test_cross_feature_matrix.py` | Tier 3 | 8 | 100% | 0.001s |
| `test_real_world_scenarios.py` | Tier 4 | 5 | 100% | 0.016s |
| **TOTAL** | **All 4 Tiers** | **93** | **100% (93/93)** | **~0.25s** |
