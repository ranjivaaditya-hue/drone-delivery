// UI tests with mock delivery states (no server needed).
import 'package:drone_delivery_app/main.dart';
import 'package:drone_delivery_app/src/app_state.dart';
import 'package:drone_delivery_app/src/models.dart';
import 'package:drone_delivery_app/src/screens/history_screen.dart';
import 'package:drone_delivery_app/src/screens/home_screen.dart';
import 'package:drone_delivery_app/src/screens/notifications_screen.dart';
import 'package:drone_delivery_app/src/screens/warehouse_screen.dart';
import 'package:drone_delivery_app/src/theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

const _flow = ['READY', 'DEPARTED', 'DELIVERING', 'PACKAGE_DELIVERED', 'RETURNING_HOME', 'COMPLETED'];
const _headlines = {
  'READY': 'PREPARING YOUR DELIVERY',
  'DEPARTED': 'DRONE HAS TAKEN OFF',
  'DELIVERING': 'DRONE IS ON THE WAY',
  'PACKAGE_DELIVERED': 'PACKAGE DELIVERED',
  'RETURNING_HOME': 'DRONE RETURNING HOME',
  'COMPLETED': 'DELIVERY COMPLETED',
  'CANCELLED': 'DELIVERY CANCELLED',
};

Delivery mockDelivery(String status, {String id = 'DEL-001'}) {
  final reached = status == 'CANCELLED' ? ['READY', 'DEPARTED', 'CANCELLED'] : _flow.sublist(0, _flow.indexOf(status) + 1);
  final t0 = DateTime.utc(2026, 10, 5, 6, 2);
  return Delivery.fromJson({
    'delivery_id': id,
    'package_id': 'PKG-001',
    'customer_name': 'Asha Kumar',
    'drone_id': 'DRONE-001',
    'status': status,
    'timestamp': t0.toIso8601String(),
    'created_at': t0.toIso8601String(),
    'headline': _headlines[status],
    'summary': 'In progress',
    'is_active': status != 'COMPLETED' && status != 'CANCELLED',
    'demo_requested': false,
    'events': [
      for (var i = 0; i < reached.length; i++)
        {
          'event_id': '$id:${reached[i]}',
          'event': 'E$i',
          'state': reached[i],
          'source': 'DEMO',
          'evidence': 'mock',
          'level': 'info',
          'timestamp': t0.add(Duration(minutes: i * 2)).toIso8601String(),
        },
    ],
  });
}

Widget wrap(AppState state, Widget child) => AppScope(
      state: state,
      child: MaterialApp(theme: buildTheme(Brightness.light), home: child),
    );

AppState mockState(String status) => AppState()
  ..serverUrl = 'http://192.168.1.20:8000'
  ..loading = false
  ..lastUpdated = DateTime.now()
  ..current = mockDelivery(status)
  ..bridge = BridgeStatus(online: true, mode: 'demo', vehicleConnected: true, detail: 'Demo')
  ..history = [mockDelivery('COMPLETED', id: 'DEL-000')]
  ..notifications = [
    AppNotification(
        id: 'n1',
        deliveryId: 'DEL-001',
        packageId: 'PKG-001',
        state: DeliveryStatus.departed,
        title: '🚁 Drone has taken off',
        body: 'Your delivery drone has taken off and started its journey.',
        timestamp: DateTime.now()),
  ];

void main() {
  for (final status in [..._flow, 'CANCELLED']) {
    testWidgets('home renders $status', (tester) async {
      await tester.pumpWidget(wrap(mockState(status), const HomeScreen()));
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text('#DEL-001'), findsOneWidget);
      expect(find.text(_headlines[status]!), findsOneWidget);
      expect(find.text('Order confirmed'), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('timeline marks the current step while delivering', (tester) async {
    await tester.pumpWidget(wrap(mockState('DELIVERING'), const HomeScreen()));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Drone took off'), findsOneWidget);
    expect(find.text('Drone is on the way'), findsOneWidget);
    expect(find.text('NOW'), findsOneWidget);
    expect(find.text('Package delivered'), findsOneWidget);
  });

  testWidgets('other tabs render', (tester) async {
    final state = mockState('DELIVERING');
    for (final screen in const [NotificationsScreen(), HistoryScreen(), WarehouseScreen()]) {
      await tester.pumpWidget(wrap(state, screen));
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.takeException(), isNull);
    }
    await tester.pumpWidget(wrap(state, const WarehouseScreen()));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('DELIVERING'), findsWidgets);
    expect(find.text('DRONE-001'), findsOneWidget);
  });

  testWidgets('app shell starts without a server address', (tester) async {
    final state = AppState()..loading = false;
    await tester.pumpWidget(DroneDeliveryApp(state: state));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('Connect to the delivery server'), findsOneWidget);
  });

  test('server address normalisation', () {
    expect(AppState.normalizeUrl('192.168.1.20'), 'http://192.168.1.20:8000');
    expect(AppState.normalizeUrl('http://192.168.1.20:8000/'), 'http://192.168.1.20:8000');
    expect(AppState.normalizeUrl(' 10.0.0.5:9000 '), 'http://10.0.0.5:9000');
    expect(AppState.normalizeUrl(''), isNull);
  });
}
