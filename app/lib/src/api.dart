import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'models.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

/// HTTP client for the PC backend (FastAPI).
class ApiClient {
  ApiClient(this.baseUrl);

  final String baseUrl;
  final http.Client _http = http.Client();
  static const _timeout = Duration(seconds: 5);

  Future<Map<String, dynamic>> _send(String method, String path, [Map<String, dynamic>? body]) async {
    final uri = Uri.parse('$baseUrl$path');
    http.Response r;
    try {
      r = await switch (method) {
        'POST' => _http.post(uri, headers: const {'Content-Type': 'application/json'}, body: jsonEncode(body ?? {})),
        _ => _http.get(uri),
      }.timeout(_timeout);
    } on TimeoutException {
      throw ApiException('The delivery server did not answer in time.');
    } catch (_) {
      throw ApiException("Can't reach the delivery server.");
    }
    final decoded = r.body.isEmpty ? <String, dynamic>{} : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 400) {
      final detail = decoded is Map ? decoded['detail'] : null;
      throw ApiException(detail is String ? detail : 'Server error (${r.statusCode})', statusCode: r.statusCode);
    }
    return decoded as Map<String, dynamic>;
  }

  Delivery? _delivery(Map<String, dynamic> j) {
    final d = j['delivery'];
    return d == null ? null : Delivery.fromJson(d as Map<String, dynamic>);
  }

  Future<bool> health() async => (await _send('GET', '/api/health'))['status'] == 'ok';

  Future<Delivery?> currentDelivery() async => _delivery(await _send('GET', '/api/deliveries/current'));

  Future<Delivery?> delivery(String id) async => _delivery(await _send('GET', '/api/deliveries/$id'));

  Future<List<Delivery>> history() async {
    final j = await _send('GET', '/api/deliveries?status=COMPLETED,CANCELLED&limit=100');
    return [for (final d in j['deliveries'] as List) Delivery.fromJson(d as Map<String, dynamic>)];
  }

  Future<List<AppNotification>> notifications() async {
    final j = await _send('GET', '/api/notifications?limit=100');
    return [for (final n in j['notifications'] as List) AppNotification.fromJson(n as Map<String, dynamic>)];
  }

  Future<BridgeStatus> status() async => BridgeStatus.fromJson(await _send('GET', '/api/status'));

  Future<Delivery> createDelivery({String? packageId, String? customerName, String? customerPhone}) async {
    final j = await _send('POST', '/api/deliveries', {
      if (packageId != null && packageId.isNotEmpty) 'package_id': packageId,
      if (customerName != null && customerName.isNotEmpty) 'customer_name': customerName,
      if (customerPhone != null && customerPhone.isNotEmpty) 'customer_phone': customerPhone,
    });
    return _delivery(j)!;
  }

  /// Returns a warning from the server, for example when the PC bridge is not in demo mode.
  Future<String?> startDemo() async => (await _send('POST', '/api/demo/start'))['warning'] as String?;

  Future<Delivery> cancel(String id) async => _delivery(await _send('POST', '/api/deliveries/$id/cancel'))!;
}
