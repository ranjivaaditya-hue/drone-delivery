# Drone Delivery MVP: ArduPilot mission events → SMS + Android app

> **Setting this up on another laptop?** Follow [MOVING_TO_A_NEW_LAPTOP.md](MOVING_TO_A_NEW_LAPTOP.md).
> It has every step and all environment variables.

A delivery **status and notification** system for an ArduPilot drone that flies a waypoint
mission and drops a package with a servo. It does **not** control or track the drone:
Mission Planner keeps doing all of that.

```
                         DRONE (ArduPilot: waypoint mission, DO_SET_SERVO release, RTL)
                                   │ MAVLink over ELRS (FLRC)
                                   ▼
                     ELRS receiver ──► PC ──► Mission Planner   (unchanged, primary connection)
                                               │  Ctrl-F ▸ MAVLink: read-only copy to UDP 14551
                                               ▼
                               pc_bridge (Python, pymavlink)     listens only, never transmits
                               MAVLink monitor → event detector → state machine
                                   │                         │
                                   ▼                         ▼
                          SMS (Mock / Twilio)        backend (FastAPI + SQLite) :8000
                          customer + warehouse               │  delivery states only
                                                             ▼
                                                  Android app (Flutter): customer + warehouse
```

The app only ever receives the delivery state:
`READY → DEPARTED → DELIVERING → PACKAGE_DELIVERED → RETURNING_HOME → COMPLETED`.
It never gets a map, position, ETA, altitude, speed, battery, or any raw MAVLink.

---

## 1. What is in this folder

| Path | What it is |
|---|---|
| `app/` | Flutter Android app (Home, Delivery status, Notifications, History, Warehouse mode) |
| `app/android/.../DeliveryWatchService.kt` | Native foreground service: delivery notifications while the app is in the background (no Firebase) |
| `backend/app.py` | FastAPI server for the app and the bridge |
| `backend/db.py` | SQLite storage, `backend/data/deliveries.db` |
| `pc_bridge/main.py` | Bridge entry point: live MAVLink, `--demo`, or `--replay file.tlog` |
| `pc_bridge/mavlink_monitor.py` | Passive MAVLink observer: MAVLink messages → mission events, each with its evidence |
| `pc_bridge/demo_source.py` | `DemoEventSource`: a full simulated mission, no drone needed |
| `pc_bridge/mission_state.py` | Delivery state machine (forward only, deduplicated) |
| `pc_bridge/notification_service.py` | `SMSProvider` → `MockSMSProvider` / `TwilioSMSProvider`, plus the SMS ledger |
| `pc_bridge/api_client.py` | Backend client with a persistent outbox (nothing is lost if the backend restarts) |
| `pc_bridge/config.py` | `.env` settings and the Mission Planner `.waypoints` parser |
| `mission/delivery_mission.waypoints` | Example mission with your layout (takeoff, WP, delivery WP, DO_SET_SERVO, RTL) |
| `tools/` | `build_apk.cmd`, `start_demo.cmd`, `start_live.cmd`, `sitl_delivery_test.py` |
| `.env.example` | All settings. Copy it to `.env` |

---

## 2. One-time setup (PC, Windows)

Python 3.11 or newer. These commands use the virtual-environment Python directly, so no
`Activate.ps1` is needed and PowerShell's script policy doesn't matter.

```bash
cd "D:\claude playground\drone_delivery"
```
```bash
python -m venv .venv
```
```bash
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt -r pc_bridge\requirements.txt
```
```bash
copy .env.example .env
```

Edit `.env`: at least `WAREHOUSE_PHONE` and `DEFAULT_CUSTOMER_PHONE` (E.164, e.g. `+919876543210`).
Leave `SMS_PROVIDER=mock` until the rest works.

---

## 3. Demo without the drone (start here)

Double-click `tools\start_demo.cmd`. It opens two windows. Or run the two commands yourself:

```bash
.venv\Scripts\python.exe backend\app.py
```
```bash
.venv\Scripts\python.exe pc_bridge\main.py --demo
```

The backend prints the address for the phone, for example `http://192.168.1.23:8000`.

On the phone:

1. Open **Drone Delivery** → gear icon → enter that address → **Save**.
2. Home shows the current delivery (`#DEL-001`, *Preparing your delivery*).
3. **Warehouse** tab → **Start demo mission**.
4. Over about 50 s, Home goes **Drone has taken off → Drone is on the way → Package delivered →
   Drone returning home → Delivery completed**. Each change also arrives as a phone notification.
5. The bridge window prints every SMS (mock): **3 to the customer, 4 to the warehouse**. They are also
   in `pc_bridge\data\sms_outbox.log`.
6. The demo sends `PACKAGE_RELEASED` **three times** on purpose. The log shows
   `Duplicate PACKAGE_RELEASED ignored` twice, and only one SMS goes out.

Tap **Start demo mission** again for the next run. It creates `DEL-002`, and so on.
To start without the phone, use `pc_bridge\main.py --demo --autostart`. Demo speed is `DEMO_STEP_SECONDS` in `.env`.

**Step through the phases yourself.** One command per phase, with only the backend running (stop
any `--demo` bridge first). Each command pushes one event through the real state machine, SMS and
backend, then prints the next command:

```bash
.venv\Scripts\python.exe pc_bridge\main.py --event TAKEOFF
```
```bash
.venv\Scripts\python.exe pc_bridge\main.py --event EN_ROUTE
```
```bash
.venv\Scripts\python.exe pc_bridge\main.py --event PACKAGE_RELEASED
```
```bash
.venv\Scripts\python.exe pc_bridge\main.py --event RTL_STARTED
```
```bash
.venv\Scripts\python.exe pc_bridge\main.py --event HOME_COMPLETED
```

Running `PACKAGE_RELEASED` twice shows the duplicate protection: no state change and no second SMS.
`DELIVERY_WAYPOINT_REACHED`, `MISSION_STARTED` and `LANDING` only add lines to the Warehouse event log.

---

## 4. Build and install the Android app

The toolchain was installed for you under `D:\dev`: Flutter 3.47.6, JDK 17, Android SDK 36 and NDK 28.2.

```bash
tools\build_apk.cmd
```

That script just sets the paths and runs the required command inside `app\`:

```bash
flutter build apk --release
```

**The APK is generated at:**

```
D:\claude playground\drone_delivery\app\build\app\outputs\flutter-apk\app-release.apk
```

Install it in one of two ways:
- Copy `app-release.apk` to the phone (USB, Drive, ...). Open it and allow *Install unknown apps* for the file manager.
- Or use USB debugging:

  ```bash
  D:\dev\android-sdk\platform-tools\adb.exe install -r app\build\app\outputs\flutter-apk\app-release.apk
  ```

On first start, Android 13+ asks for notification permission. Allow it.
For reliable background alerts on Xiaomi, Oppo, Vivo or Realme phones, set
*Settings → Apps → Drone Delivery → Battery → Unrestricted*.

**Signing.** Without extra setup, the release APK is signed with the debug key. That is fine for
your own phones. For a real release key, create `app\android\key.properties`
(`storeFile`, `storePassword`, `keyAlias`, `keyPassword`). `app\android\app\build.gradle.kts`
uses it automatically.

**The phone must reach the PC** on port 8000, on the same Wi-Fi:
- When Windows Firewall asks about Python, allow **Private networks**. The Wi-Fi profile must be *Private*, not *Public*.
- Check it from the phone's browser: `http://<PC-IP>:8000/api/health` must show `{"status":"ok",...}`.
- If it is still blocked, add the rule yourself in an *administrator* terminal:

  ```bash
  netsh advfirewall firewall add rule name="Drone Delivery API" dir=in action=allow protocol=TCP localport=8000 profile=private
  ```

---

## 5. Real drone: MAVLink/UDP configuration on the PC

### 5.0 Telemetry radio on a USB serial port (COM port)

Set in `.env`: `MAVLINK_CONNECTION=COM5` and `MAVLINK_BAUD=57600` (use your port from Device Manager →
Ports, and the radio's baud rate). The bridge opens the port **listen-only**. Windows lets only one program
open a COM port, so either disconnect Mission Planner from that port while the bridge runs, or keep
Mission Planner on the port and use the forwarding in 5.1 (`MAVLINK_CONNECTION=udpin:0.0.0.0:14551`).
If the radio is unplugged the bridge keeps retrying every 3 s. With no ground station connected,
ArduPilot only sends the streams set in `SRx_*` parameters, so set `SRx_EXT_STAT`, `SRx_POSITION` and
`SRx_RC_CHAN` to at least 2 for the port the radio uses (HEARTBEAT, and so the arming notification, always works).

**`DEPART_ON_ARM=true` (temporary mode):** arming the drone counts as "package picked up / departed". The app
and the SMS show the first step immediately, in any flight mode. Set it to `false` to wait for the real takeoff.

### 5.1 Give the bridge a read-only copy of the stream

Mission Planner stays connected exactly as today. The bridge must **not** open the same COM
port: Windows allows one process per port. It must **not** bind Mission Planner's UDP port
either: Windows hands each datagram to only one of the sockets. The bridge gets **its own copy**
on UDP **14551**.

**Option A (recommended): Mission Planner forwards a copy.** No extra software, and Mission Planner stays primary.

1. Connect Mission Planner to the drone as usual (your ELRS link).
2. Press **Ctrl+F** → click **MAVLink** (the forwarding tool).
3. Choose **UDP Client** and enter **127.0.0.1**, port **14551**.
4. Leave **Write access unticked**. The copy then cannot change parameters or control the
   drone, which guarantees the bridge is read-only.
5. Start the bridge (`tools\start_live.cmd`). It should log `Locked onto vehicle: system id 1`.

Mission Planner can forward to only one destination, and you have to turn it on again after
restarting Mission Planner. See the
[Mission Planner advanced tools docs](https://ardupilot.org/planner/docs/common-mp-tools.html).

**Option B: MAVProxy splits the link**, if you want the bridge independent of Mission Planner:

```bash
mavproxy.exe --master=COM5,460800 --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
```

Replace `COM5,460800` with your ELRS link, or `udpin:0.0.0.0:14560` if your ELRS forwarder sends
UDP (then point the forwarder at 14560). Mission Planner connects to **UDP 14550**; the bridge
listens on 14551.

Bridge setting in `.env` (the default): `MAVLINK_CONNECTION=udpin:0.0.0.0:14551`

### 5.2 Telemetry streams over ELRS

Bandwidth on ELRS is limited, so check that the messages the bridge needs are actually sent.
Every 30 s the bridge logs a **Link check** with per-message rates, and warns when something is missing:

| Message | ArduPilot stream | Needed for | Minimum |
|---|---|---|---|
| HEARTBEAT | always ~1 Hz | armed / mode / landed (disarm) | — |
| MISSION_CURRENT | `SRx_EXT_STAT` (Mission Planner: *Mode/Status*) | mission progress, RTL leg, release fallback | 1 Hz |
| SERVO_OUTPUT_RAW | `SRx_RC_CHAN` (Mission Planner: *RC*) | **direct servo-PWM release evidence** | 1 Hz |
| GLOBAL_POSITION_INT | `SRx_POSITION` | airborne confirmation | 1 Hz |
| STATUSTEXT, MISSION_ITEM_REACHED | sent as events | fastest evidence; can be lost on a lossy link | — |

`SRx_` is the MAVLink port the ELRS link is on (SR0 = first MAVLink serial port, SR1 = second, ...).
Mission Planner also requests rates when it connects (*Config → Planner → Telemetry Rates*).
Use **MAVLink2** (`SERIALx_PROTOCOL = 2`). Servo outputs 9–16 only exist in MAVLink2.

### 5.3 Mission layout, and when ArduPilot actually fires the servo

```
#  Command            Param 1      Param 2     Alt
0  HOME
1  TAKEOFF                                      20 m
2  WAYPOINT                                     20 m
3  WAYPOINT           3  (hold s)               20 m   ← delivery point
4  DO_SET_SERVO       9  (servo)   1900 (PWM)          ← release
5  RETURN_TO_LAUNCH                                    ← flies home, lands, disarms
```

Things that are easy to get wrong (all verified in the ArduPilot source and in SITL):

- A **DO command runs when the NAV item before it completes**. Here the servo fires after the drone
  reaches item 3 and holds 3 s. The RTL starts in the same instant. To hover while the package
  falls, insert `LOITER_TIME` (e.g. 5 s) between DO_SET_SERVO and RTL.
- The servo output must be free for DO_SET_SERVO: **`SERVO9_FUNCTION = 0`** (or RC passthrough).
- **Recommended:** add `DO_SET_SERVO 9 <closed PWM>` *before* TAKEOFF. The latch is then closed at the start of
  every mission. The servo otherwise stays at 1900 after a drop until something changes it or the FC
  reboots, and then the next flight cannot use servo-PWM evidence. The bridge detects this case and
  falls back to the mission text or sequence; see section 6.
- Set **`MIS_RESTART = 1`** (restart the mission from the beginning). With the default, a mission that
  was interrupted *resumes* mid-way the next time AUTO is engaged. Also, a **completed** mission does
  not start again until you leave AUTO and re-enter it: arming while still in AUTO does nothing, and
  ArduPilot disarms after a few seconds. SITL showed this.

**Tell the bridge your mission.** In Mission Planner's PLAN screen, use **Save File**. Put the
`.waypoints` file in `mission\` and set `MISSION_FILE` in `.env`. The bridge reads the takeoff,
delivery waypoint, release command and RTL item numbers from it, plus the servo channel and
release PWM. The default file matches the layout above. You can override any value with
`TAKEOFF_SEQ`, `DELIVERY_WP_SEQ`, `RELEASE_SEQ`, `RTL_SEQ`, `RELEASE_SERVO_CHANNEL` and
`RELEASE_SERVO_PWM`. `DO_GRIPPER` (release) is recognised too.

### 5.4 Check against your real flights (Phase 8 / 9)

Mission Planner records every session as a `.tlog` (default: `Documents\Mission Planner\logs\...`).
Replay any of them through the detector. This prints what would have been detected and on what
evidence, with no SMS and no backend:

```bash
.venv\Scripts\python.exe pc_bridge\main.py --replay "C:\path\to\your-flight.tlog"
```

Suggested order on the real drone:
1. Bench, props off, no package: arm, AUTO, check the Link check line and the `SERVO_OUTPUT_RAW` rate.
2. Fly the mission with `SMS_PROVIDER=mock`, watch the bridge log, then `--replay` the tlog.
3. Switch to Twilio only after the logged events match the flight.

---

## 6. How each event is detected, and what cannot be detected

The bridge only uses messages that ArduPilot really sends. Every rule below was checked in the
ArduPilot source (Copter 4.3 / 4.4 / 4.5 / master) **and** observed on **ArduCopter 4.7.1 SITL**
flying this exact mission. That included two back-to-back deliveries over a link dropping **30% of packets**.

| State | Event | MAVLink evidence (first to arrive wins) |
|---|---|---|
| — | MISSION_STARTED | HEARTBEAT: armed **and** flight mode AUTO |
| **DEPARTED** | TAKEOFF | in AUTO **and airborne**: `GLOBAL_POSITION_INT.relative_alt ≥ 1.5 m`, *or* takeoff item completed (`MISSION_ITEM_REACHED #1`, `MISSION_CURRENT` moved past #1), *or* `EXTENDED_SYS_STATE` in-air (if streamed) |
| **DELIVERING** | EN_ROUTE | takeoff item done: `MISSION_ITEM_REACHED #1`, `MISSION_CURRENT > 1`, or `STATUSTEXT "Mission: 2 WP"` |
| — | DELIVERY_WAYPOINT_REACHED | `MISSION_ITEM_REACHED #3`, `STATUSTEXT "Reached command #3"`, or `MISSION_CURRENT > 3`. **Logged only. It never counts as delivered.** |
| **PACKAGE_DELIVERED** | PACKAGE_RELEASED | ① `SERVO_OUTPUT_RAW servo9_raw` changes from a closed value to 1900 ± 100 µs during the mission. ② `STATUSTEXT "Mission: 4 SetServo"` (the mission engine started the release command). ③ *Fallback:* `MISSION_CURRENT` jumps from ≤ 3 to > 4, i.e. the mission passed the DO_SET_SERVO item. Used only if ① and ② do not arrive within 3 s. Disable it with `RELEASE_SEQ_FALLBACK=false`. |
| **RETURNING_HOME** | RTL_STARTED | `STATUSTEXT "Mission: 5 RTL"`, `MISSION_CURRENT == 5`, or HEARTBEAT mode RTL / SMART_RTL / AUTO_RTL (manual or failsafe). **Counts only after the release.** |
| **COMPLETED** | HOME_COMPLETED | `MISSION_ITEM_REACHED #5` (ArduCopter completes the RTL item only after landing), `MISSION_CURRENT.mission_state = COMPLETE`, or HEARTBEAT *disarmed* after the return |
| — | LANDING | HEARTBEAT mode LAND, `"Mission: N Land"`, or `EXTENDED_SYS_STATE` LANDING (logged only) |

**ArduPilot facts this design depends on** (source + SITL):
1. `MISSION_CURRENT.seq` only ever reports **NAV** items. In SITL it went **3 → 5**, never 4.
   The DO_SET_SERVO can't be "seen" there directly.
2. **No `MISSION_ITEM_REACHED` is sent for DO_SET_SERVO.** AP_Mission completes DO items itself.
   It *is* sent for takeoff, waypoints and RTL.
3. `"Mission: <seq> <type>"` is sent when *any* item starts. `"Mission: 1 Takeoff"` arrives **before
   arming and liftoff**, so it is not used as takeoff evidence.
4. A mission **RTL item keeps the flight mode AUTO** (an RTL sub-mode inside AUTO). HEARTBEAT never says RTL for it.
5. `servo9_raw` read 0 until the DO_SET_SERVO, then **1900 in the same instant as `"Mission: 4 SetServo"`**,
   and it stayed 1900 afterwards.
6. `EXTENDED_SYS_STATE` is not in any default ArduPilot stream. It is used only if present.

**What cannot be detected reliably. Stated plainly:**
- **Whether the package physically left the drone.** `SERVO_OUTPUT_RAW` is the PWM the flight
  controller *outputs*, not the servo's position or a payload sensor. `PACKAGE_DELIVERED` means
  "the release PWM was output / the release command ran". A jammed latch would still be reported as
  delivered. Detecting the drop itself needs a sensor, e.g. a limit switch read by the FC. That is
  out of scope for this MVP.
- **"Landed at home"** is not a MAVLink message. It is inferred: the RTL item completed, the mission
  completed, or the drone disarmed after the return leg. With `RTL_ALT_FINAL > 0` the drone hovers
  instead of landing, so COMPLETED comes only once you land and disarm.
- **The landing phase inside RTL** has no streamed message by default (see fact 6).
- **One-shot messages can be lost on ELRS.** STATUSTEXT and MISSION_ITEM_REACHED are sent once. Every
  state therefore also has a periodic source: MISSION_CURRENT, SERVO_OUTPUT_RAW, HEARTBEAT.
  Fallback ③ ("mission passed the servo command") is weaker evidence than ①, and the evidence text
  in the warehouse log says which one was used.
- **A servo left at the release PWM** from the previous drop cannot prove a new drop. The bridge
  logs `SERVO9 is already at the release PWM` and relies on ② or ③ for that flight.

Every event, with the exact evidence, appears in the app's **Warehouse → Event log** and in the bridge log.

---

## 7. State machine and duplicate protection

`pc_bridge/mission_state.py` turns events into states:

| Event (latched fact) | Gives state |
|---|---|
| TAKEOFF | DEPARTED |
| EN_ROUTE | DELIVERING |
| PACKAGE_RELEASED | PACKAGE_DELIVERED (implies the earlier states) |
| RTL_STARTED **after** the release | RETURNING_HOME |
| HOME_COMPLETED after that return | COMPLETED |

Duplicates are stopped at five layers:

1. **Detector:** one event per kind per flight. RTL fires once per return.
2. **State machine:** facts are latched, the state only moves forward, and each state is entered once.
   Out-of-order evidence is handled. Example: the RTL text arrives 0.5 s before the servo sample, and the
   states still go PACKAGE_DELIVERED → RETURNING_HOME in that order.
3. **SMS ledger:** `pc_bridge\data\bridge.db`, table `sms_log`. The key `DEL-001:PACKAGE_DELIVERED:customer`
   is claimed *before* sending. It is never sent twice, even after a bridge restart.
4. **Backend:** `event_id` = `DEL-001:PACKAGE_DELIVERED`. Repeated posts are ignored and the status never moves backwards.
5. **Phone:** the last notified `delivery:state` is stored, so the phone never shows the same update twice.

Safety rules: a failsafe RTL *before* the drop never produces "delivered". The customer keeps seeing
*on the way*, and the warehouse log gets a warning. If the drone lands without a detected release,
the warehouse sees `FLIGHT_ENDED_WITHOUT_RELEASE`. Then use **Warehouse → Cancel / close delivery**.
If the package was already delivered, closing marks the delivery COMPLETED; otherwise it becomes CANCELLED.

---

## 8. SMS

| Recipient | DEPARTED | PACKAGE_DELIVERED | RETURNING_HOME | COMPLETED |
|---|---|---|---|---|
| Customer | 🚁 Your package is on the way! | 📦 Your package has been delivered! | — | 🏠 Delivery completed. |
| Warehouse | Delivery mission started | Package released at delivery location | Drone is returning to warehouse | Mission completed |

The texts are exactly the ones in the specification. See `notification_service.py`.

- **Mock (default):** prints a box per SMS and appends it to `pc_bridge\data\sms_outbox.log`.
- **Twilio:** set these in `.env` (never in code). `twilio` is already in `pc_bridge\requirements.txt`.
  ```
  SMS_PROVIDER=twilio
  TWILIO_ACCOUNT_SID=ACxxxxxxxx
  TWILIO_AUTH_TOKEN=xxxxxxxx
  TWILIO_FROM_NUMBER=+1xxxxxxxxxx      (or TWILIO_MESSAGING_SERVICE_SID=MGxxxx)
  ```
  A trial account can only send to verified numbers.
- **Indian numbers (+91):** business SMS in India must be **DLT-registered** (sender ID and templates,
  TRAI rules). International routes, including Twilio's, may be filtered. For production in India, use a
  DLT-registered Indian SMS gateway. Adding one is a single class that implements `SMSProvider.send(to, body)`.
- The emoji make each SMS Unicode (70 characters per segment), so each message is about 2 segments.

Failed sends are retried up to 3 attempts, and are never sent twice.

---

## 9. Backend API (FastAPI + SQLite)

`backend/data/deliveries.db` has one table, `deliveries`. Its columns are `delivery_id, package_id,
customer_name, customer_phone, warehouse_phone, drone_id, status, timestamp, event_history`
(a JSON list), plus `created_at, demo_requested`. Interactive docs: `http://<PC-IP>:8000/docs`.

| Endpoint | Used by | Purpose |
|---|---|---|
| `GET /api/deliveries/current` | app | latest delivery (state, texts, events). **No phone numbers** |
| `GET /api/deliveries?status=COMPLETED,CANCELLED` | app | history |
| `GET /api/deliveries/{id}` | app | one delivery |
| `GET /api/notifications` | app | notification history (every state change) |
| `GET /api/status` | app | whether the PC bridge is online, its mode (live/demo), whether the drone link is up |
| `POST /api/deliveries` | app (Warehouse) | prepare the next delivery (edits it if one is still READY) |
| `POST /api/deliveries/{id}/cancel` | app (Warehouse) | close an unfinished delivery |
| `POST /api/demo/start` | app (Warehouse) | ask the demo bridge to fly a simulated mission |
| `GET /api/drones/{drone}/active-delivery` | bridge | active delivery, with phone numbers for SMS |
| `POST /api/deliveries/{id}/events` | bridge | state or info event. Idempotent by `event_id` |
| `POST /api/bridge/heartbeat` | bridge | bridge alive, mode, drone link |

If you prepare no delivery before a flight, the bridge creates one at takeoff from the `DEFAULT_*` values in `.env`.

---

## 10. Tests

```bash
.venv\Scripts\python.exe -m pip install pytest httpx
```
```bash
.venv\Scripts\python.exe -m pytest pc_bridge\tests backend\tests
```

There are 58 tests: state machine, SMS dedup, detector on real MAVLink2 packets, mission-file
parser and API. That includes **17 replays of real ArduCopter 4.7.1 SITL flights** in
`pc_bridge/tests/data/*.tlog`, with STATUSTEXT, MISSION_ITEM_REACHED, SERVO_OUTPUT_RAW or position
data removed, or 30% random packet loss. All must still give every state, in order, exactly once.

App tests (UI with mock states):

```bash
cd app
```
```bash
flutter test
```

`tools/sitl_delivery_test.py` re-flies the mission on ArduCopter SITL. It plays Mission Planner's
role: it uploads the mission, arms in AUTO, and mirrors MAVLink to UDP 14551, optionally lossy
(`--drop 0.3`). Use it with the bridge and backend running. The ArduCopter 4.7.1 SITL binary
(from `firmware.ardupilot.org`) is already in your WSL Ubuntu at `/root/sitl`. Start it with:

```bash
wsl -d Ubuntu-24.04 -u root -- bash /root/sitl/run.sh
```
```bash
.venv\Scripts\python.exe tools\sitl_delivery_test.py --drop 0.3
```

---

## 11. Troubleshooting

| Symptom | Fix |
|---|---|
| App: *Can't reach the delivery server* | Same Wi-Fi? Firewall (section 4)? Open `http://<PC-IP>:8000/api/health` in the phone browser. |
| Warehouse tab: *Event monitor offline* | Start `pc_bridge\main.py` (or `--demo`). |
| Bridge: *No ArduPilot HEARTBEAT received yet* | Mission Planner forwarding is not on, or uses the wrong port (section 5.1). |
| Bridge: *Not receiving SERVO_OUTPUT_RAW* | Raise the RC stream rate (section 5.2). Release then still works through STATUSTEXT or the fallback. |
| Events stop after DELIVERING | Check `MISSION_FILE` / `*_SEQ` against Mission Planner's item numbers. Replay the tlog (section 5.4). |
| No phone notifications | Allow notifications. Battery → *Unrestricted*. The app must have seen the delivery while it was active, so open it once. |
| APK build: *sdkmanager did not install NDK* | The new `sdkmanager.bat` breaks on `;` on Windows. Install with a package file: write `ndk;28.2.13676358` into `pkgs.txt`, then run `sdkmanager --package_file=pkgs.txt`. |

---

## 12. Known limitations (MVP)

- **No authentication.** Anyone on the same Wi-Fi can read statuses and create or cancel deliveries.
  Before using it beyond a closed network, add an API key and HTTPS.
- One drone (`DRONE_ID`) and one active delivery at a time.
- The phone reaches the backend over the local network. For customers elsewhere, host `backend/`
  on a server and point the bridge's `API_BASE_URL` and the app at it.
- Background updates use an Android foreground service: a small *Tracking your delivery*
  notification shows while a delivery is active. It needs no Firebase. Android 15 limits this type
  of service to about 6 h a day.
- The **Twilio code path has not been run against a live account** (no credentials here). The mock
  provider and the full SMS logic (templates, recipients, dedup, retry) are tested.
