import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'api.dart';
import 'models.dart';
import 'tracking.dart';

/// App-wide state. It polls the PC backend while the app is visible.
/// Background notifications come from the native tracking service.
class AppState extends ChangeNotifier with WidgetsBindingObserver {
  static const _kServerUrl = 'server_url';
  static const _kSeenAt = 'notifications_seen_at';
  static const _kAskedPermission = 'asked_notification_permission';
  static const pollEvery = Duration(seconds: 2);

  SharedPreferences? _prefs;
  ApiClient? _api;
  Timer? _timer;
  int _tick = 0;
  bool _polling = false;
  String? _trackingKey;
  DateTime? _seenAt;

  String? serverUrl;
  Delivery? current;
  List<AppNotification> notifications = const [];
  List<Delivery> history = const [];
  BridgeStatus? bridge;
  bool loading = true;
  String? error;
  DateTime? lastUpdated;

  bool get configured => serverUrl != null;
  bool get connected => configured && error == null && lastUpdated != null;

  Future<void> init() async {
    WidgetsBinding.instance.addObserver(this);
    _prefs = await SharedPreferences.getInstance();
    serverUrl = _prefs!.getString(_kServerUrl);
    final seen = _prefs!.getString(_kSeenAt);
    _seenAt = seen == null ? null : DateTime.tryParse(seen);
    if (serverUrl != null) _api = ApiClient(serverUrl!);
    loading = configured;
    notifyListeners();
    _startPolling();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _startPolling();
    } else if (state == AppLifecycleState.paused) {
      _timer?.cancel();
      _timer = null;
    }
  }

  void _startPolling() {
    _timer?.cancel();
    _timer = Timer.periodic(pollEvery, (_) => _poll());
    _poll(full: true);
  }

  Future<void> refreshAll() => _poll(full: true);

  Future<void> _poll({bool full = false}) async {
    final api = _api;
    if (api == null || _polling) return;
    _polling = true;
    try {
      _tick++;
      final cur = await api.currentDelivery();
      final st = await api.status();
      if (full || _tick % 4 == 0 || cur?.updatedAt != current?.updatedAt) {
        notifications = await api.notifications();
        history = await api.history();
        if (_seenAt == null && notifications.isNotEmpty) markNotificationsRead();
      }
      current = cur;
      bridge = st;
      error = null;
      lastUpdated = DateTime.now();
      _syncTracking();
    } on ApiException catch (e) {
      error = e.message;
    } finally {
      _polling = false;
      loading = false;
      notifyListeners();
    }
  }

  /// Start the native watcher once for each active delivery.
  void _syncTracking() {
    final d = current;
    final url = serverUrl;
    if (d == null || url == null || !d.isActive) return;
    final key = '${d.id}|$url';
    if (key == _trackingKey) return;
    _trackingKey = key;
    TrackingService.start(url);
  }

  // ------------------------------------------------------------ settings
  static String? normalizeUrl(String raw) {
    var s = raw.trim();
    if (s.isEmpty) return null;
    if (!s.startsWith('http://') && !s.startsWith('https://')) s = 'http://$s';
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    final uri = Uri.tryParse(s);
    if (uri == null || uri.host.isEmpty) return null;
    if (!uri.hasPort && uri.scheme == 'http') s = '$s:8000';
    return s;
  }

  /// Checks the server, then saves it. Returns an error message, or null on success.
  Future<String?> setServerUrl(String raw) async {
    final url = normalizeUrl(raw);
    if (url == null) return 'Enter an address like 192.168.1.20:8000';
    try {
      await ApiClient(url).health();
    } on ApiException catch (e) {
      return e.message;
    }
    serverUrl = url;
    _api = ApiClient(url);
    await _prefs?.setString(_kServerUrl, url);
    current = null;
    notifications = const [];
    history = const [];
    error = null;
    loading = true;
    _trackingKey = null;
    notifyListeners();
    await refreshAll();
    return null;
  }

  Future<String?> testServer(String raw) async {
    final url = normalizeUrl(raw);
    if (url == null) return 'Enter an address like 192.168.1.20:8000';
    try {
      await ApiClient(url).health();
      return null;
    } on ApiException catch (e) {
      return e.message;
    }
  }

  // ------------------------------------------------------------ notifications
  int get unreadCount {
    final seen = _seenAt;
    if (seen == null) return 0;
    return notifications.where((n) => n.timestamp != null && n.timestamp!.isAfter(seen)).length;
  }

  void markNotificationsRead() {
    _seenAt = DateTime.now();
    _prefs?.setString(_kSeenAt, _seenAt!.toIso8601String());
    notifyListeners();
  }

  Future<void> requestNotificationPermissionOnce() async {
    if (_prefs == null || (_prefs!.getBool(_kAskedPermission) ?? false)) return;
    await _prefs!.setBool(_kAskedPermission, true);
    await TrackingService.requestPermission();
  }

  // ------------------------------------------------------------ warehouse actions
  ApiClient _requireApi() {
    final api = _api;
    if (api == null) throw ApiException('Set the server address first (gear icon on Home).');
    return api;
  }

  Future<Delivery> createDelivery({String? packageId, String? customerName, String? customerPhone}) async {
    final d = await _requireApi()
        .createDelivery(packageId: packageId, customerName: customerName, customerPhone: customerPhone);
    await refreshAll();
    return d;
  }

  Future<String?> startDemo() async {
    final warning = await _requireApi().startDemo();
    await refreshAll();
    return warning;
  }

  Future<void> cancelCurrent() async {
    final d = current;
    if (d == null) return;
    await _requireApi().cancel(d.id);
    await refreshAll();
  }

  Future<Delivery?> loadDelivery(String id) => _requireApi().delivery(id);

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timer?.cancel();
    super.dispose();
  }
}

/// Makes [AppState] available to the widget tree and rebuilds dependents when it changes.
class AppScope extends InheritedNotifier<AppState> {
  const AppScope({super.key, required AppState state, required super.child}) : super(notifier: state);

  static AppState of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<AppScope>()!.notifier!;

  static AppState read(BuildContext context) => context.getInheritedWidgetOfExactType<AppScope>()!.notifier!;
}
