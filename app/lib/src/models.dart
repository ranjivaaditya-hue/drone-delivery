/// Data the app receives from the PC backend. Only high-level delivery
/// states are sent here: no MAVLink and no telemetry.
library;

enum DeliveryStatus {
  ready('READY', 'Ready'),
  departed('DEPARTED', 'Departed'),
  delivering('DELIVERING', 'Delivering'),
  packageDelivered('PACKAGE_DELIVERED', 'Package delivered'),
  returningHome('RETURNING_HOME', 'Returning home'),
  completed('COMPLETED', 'Completed'),
  cancelled('CANCELLED', 'Cancelled'),
  unknown('UNKNOWN', 'Unknown');

  const DeliveryStatus(this.wire, this.label);
  final String wire;
  final String label;

  static DeliveryStatus parse(String? value) {
    for (final s in values) {
      if (s.wire == value) return s;
    }
    return unknown;
  }

  /// Position in the normal flow READY -> ... -> COMPLETED.
  int get flowIndex => switch (this) {
        ready => 0,
        departed => 1,
        delivering => 2,
        packageDelivered => 3,
        returningHome => 4,
        completed => 5,
        cancelled => 6,
        unknown => -1,
      };

  bool get isTerminal => this == completed || this == cancelled;
  bool get isFlying => this == departed || this == delivering || this == returningHome;
}

DateTime? _time(Object? v) => v is String ? DateTime.tryParse(v)?.toLocal() : null;

class DeliveryEvent {
  DeliveryEvent({
    required this.eventId,
    required this.event,
    required this.state,
    required this.source,
    required this.evidence,
    required this.level,
    required this.timestamp,
    this.title,
  });

  factory DeliveryEvent.fromJson(Map<String, dynamic> j) => DeliveryEvent(
        eventId: j['event_id'] as String? ?? '',
        event: j['event'] as String? ?? '',
        state: j['state'] == null ? null : DeliveryStatus.parse(j['state'] as String?),
        source: j['source'] as String? ?? '',
        evidence: j['evidence'] as String? ?? '',
        level: j['level'] as String? ?? 'info',
        timestamp: _time(j['timestamp']),
        title: j['title'] as String?,
      );

  final String eventId;
  final String event;
  final DeliveryStatus? state; // null = informational event (no state change)
  final String source;
  final String evidence;
  final String level;
  final DateTime? timestamp;
  final String? title;

  bool get isWarning => level == 'warning';
}

class Delivery {
  Delivery({
    required this.id,
    required this.packageId,
    required this.customerName,
    required this.droneId,
    required this.status,
    required this.updatedAt,
    required this.createdAt,
    required this.headline,
    required this.summary,
    required this.isActive,
    required this.demoRequested,
    required this.events,
  });

  factory Delivery.fromJson(Map<String, dynamic> j) => Delivery(
        id: j['delivery_id'] as String,
        packageId: j['package_id'] as String? ?? '',
        customerName: j['customer_name'] as String? ?? '',
        droneId: j['drone_id'] as String? ?? '',
        status: DeliveryStatus.parse(j['status'] as String?),
        updatedAt: _time(j['timestamp']),
        createdAt: _time(j['created_at']),
        headline: j['headline'] as String? ?? '',
        summary: j['summary'] as String? ?? '',
        isActive: j['is_active'] as bool? ?? false,
        demoRequested: j['demo_requested'] as bool? ?? false,
        events: [
          for (final e in (j['events'] as List? ?? const [])) DeliveryEvent.fromJson(e as Map<String, dynamic>),
        ],
      );

  final String id;
  final String packageId;
  final String customerName;
  final String droneId;
  final DeliveryStatus status;
  final DateTime? updatedAt;
  final DateTime? createdAt;
  final String headline;
  final String summary;
  final bool isActive;
  final bool demoRequested;
  final List<DeliveryEvent> events;

  /// When the delivery entered [state], if it did.
  DateTime? timeOf(DeliveryStatus state) {
    for (final e in events) {
      if (e.state == state) return e.timestamp;
    }
    return null;
  }

  /// Furthest point of the normal flow that was reached. Useful for cancelled deliveries.
  DeliveryStatus get furthestReached {
    var best = DeliveryStatus.ready;
    for (final e in events) {
      final s = e.state;
      if (s != null && s != DeliveryStatus.cancelled && s.flowIndex > best.flowIndex) best = s;
    }
    return best;
  }

  DateTime? get finishedAt => status.isTerminal ? updatedAt : null;
}

class AppNotification {
  AppNotification({
    required this.id,
    required this.deliveryId,
    required this.packageId,
    required this.state,
    required this.title,
    required this.body,
    required this.timestamp,
  });

  factory AppNotification.fromJson(Map<String, dynamic> j) => AppNotification(
        id: j['id'] as String? ?? '',
        deliveryId: j['delivery_id'] as String? ?? '',
        packageId: j['package_id'] as String? ?? '',
        state: DeliveryStatus.parse(j['state'] as String?),
        title: j['title'] as String? ?? '',
        body: j['body'] as String? ?? '',
        timestamp: _time(j['timestamp']),
      );

  final String id;
  final String deliveryId;
  final String packageId;
  final DeliveryStatus state;
  final String title;
  final String body;
  final DateTime? timestamp;
}

class BridgeStatus {
  BridgeStatus({required this.online, required this.mode, required this.vehicleConnected, required this.detail});

  factory BridgeStatus.fromJson(Map<String, dynamic> j) {
    final b = (j['bridge'] as Map<String, dynamic>?) ?? const {};
    return BridgeStatus(
      online: b['online'] as bool? ?? false,
      mode: b['mode'] as String?,
      vehicleConnected: b['vehicle_connected'] as bool? ?? false,
      detail: b['detail'] as String? ?? '',
    );
  }

  final bool online;
  final String? mode; // "live" | "demo"
  final bool vehicleConnected;
  final String detail;

  bool get isDemo => mode == 'demo';
}
