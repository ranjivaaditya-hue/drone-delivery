class NoGpsFlightDetector:
    """Uses only HEARTBEAT (armed) and VFR_HUD (baro altitude). No GPS, no mission."""
    AIRBORNE_M = 1.5       # climb above arming altitude = in transit
    LANDED_M = 0.7         # back within this of the ground level = landed
    LANDED_HOLD_S = 3.0    # must stay low this long

    def __init__(self, emit):
        self.emit = emit   # emit(event_name, evidence_text)
        self.alt = None
        self._reset()

    def _reset(self):
        self.armed = False
        self.base_alt = None
        self.in_transit = False
        self.delivered = False
        self.low_since = None

    def on_message(self, msg):
        t = msg.get_type()
        if t == "VFR_HUD":
            self.alt = msg.alt
            self._check_altitude(msg._timestamp if hasattr(msg, "_timestamp") else None)
        elif t == "HEARTBEAT":
            if msg.type == 6 or msg.autopilot == 8:   # ignore GCS heartbeats
                return
            self._check_armed(bool(msg.base_mode & 128))

    def _check_armed(self, armed):
        if armed and not self.armed:
            self._reset()
            self.armed = True
            self.base_alt = self.alt
            self.emit("TAKEOFF", "Armed: package picked up")
        elif not armed and self.armed:
            if self.in_transit and not self.delivered:
                self.delivered = True
                self.emit("PACKAGE_RELEASED", "Disarmed after flight: landed")
            self.armed = False

    def _check_altitude(self, now):
        import time
        now = time.time()
        if not self.armed or self.alt is None:
            return
        if self.base_alt is None:
            self.base_alt = self.alt
            return
        climb = self.alt - self.base_alt
        if not self.in_transit and climb >= self.AIRBORNE_M:
            self.in_transit = True
            self.emit("EN_ROUTE", f"Climbed {climb:.1f} m above start")
        elif self.in_transit and not self.delivered:
            if climb <= self.LANDED_M:
                self.low_since = self.low_since or now
                if now - self.low_since >= self.LANDED_HOLD_S:
                    self.delivered = True
                    self.emit("PACKAGE_RELEASED", "Back on the ground: landed")
            else:
                self.low_since = None