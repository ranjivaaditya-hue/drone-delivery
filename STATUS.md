# Build status — Drone Delivery MVP

_Finished: 14:50. Everything below is built and tested. See README.md for how to run it._

## Result
| # | Phase | Status |
|---|---|---|
| 1 | Flutter Android UI (mock states) | ✅ 11 widget tests, all 6 states + cancelled rendered |
| 2 | Python MAVLink event monitor | ✅ |
| 3 | Mission state machine + dedup | ✅ |
| 4 | FastAPI + SQLite backend | ✅ |
| 5 | Flutter ↔ API | ✅ driven end to end: tapped "Start demo mission" in the app UI and watched every state |
| 6 | SMS (Mock + Twilio) | ✅ mock tested; Twilio code path not run (no credentials) |
| 7 | Demo mode (DemoEventSource) | ✅ |
| 8 | Real ArduPilot MAVLink | ✅ ArduCopter 4.7.1 SITL, 3 flights through UDP 14551, including 30% packet loss |
| 9 | Waypoint + servo events | ✅ in SITL. **On your real drone + ELRS: still to do** (README §5.4) |
| 10 | `flutter build apk --release` | ✅ `app\build\app\outputs\flutter-apk\app-release.apk` (48.8 MB) |

## Numbers
- 58 Python tests: state machine, SMS dedup, detector, API, mission parser, and 17 replays of real SITL flight logs.
- 11 Flutter tests. `flutter analyze`: no issues.
- Demo run started from the app: 5 state changes, 7 SMS (3 customer + 4 warehouse), 2 duplicate releases ignored.
- SITL with 30% loss, 2 back-to-back deliveries: 14 SMS, no duplicates. The stale-servo case was handled.

## Toolchain (D:\dev)
Flutter 3.47.6, JDK 17, Android SDK 36 + NDK 28.2 (license accepted), Gradle cache, pub cache.
ArduCopter SITL 4.7.1 in WSL at `/root/sitl`.
