import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Bridge to the native Android foreground service (DeliveryWatchService.kt).
///
/// While a delivery is in progress, the service polls the server and shows a
/// notification on every state change. This keeps working when the app is in
/// the background or swiped away. No Firebase is needed.
class TrackingService {
  static const _channel = MethodChannel('drone_delivery/tracking');

  static bool get supported => !kIsWeb && defaultTargetPlatform == TargetPlatform.android;

  static Future<void> start(String serverUrl) async {
    if (!supported) return;
    try {
      await _channel.invokeMethod('startTracking', {'serverUrl': serverUrl});
    } on PlatformException catch (e) {
      debugPrint('startTracking failed: $e');
    }
  }

  static Future<void> stop() async {
    if (!supported) return;
    try {
      await _channel.invokeMethod('stopTracking');
    } on PlatformException catch (e) {
      debugPrint('stopTracking failed: $e');
    }
  }

  static Future<bool> notificationsAllowed() async {
    if (!supported) return false;
    try {
      return await _channel.invokeMethod<bool>('notificationsAllowed') ?? false;
    } on PlatformException {
      return false;
    }
  }

  /// Asks for POST_NOTIFICATIONS (Android 13+). Returns whether notifications are allowed.
  static Future<bool> requestPermission() async {
    if (!supported) return false;
    try {
      return await _channel.invokeMethod<bool>('requestNotificationPermission') ?? false;
    } on PlatformException {
      return false;
    }
  }
}
