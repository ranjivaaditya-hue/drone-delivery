import 'package:flutter/material.dart';

import 'src/app_state.dart';
import 'src/screens/history_screen.dart';
import 'src/screens/home_screen.dart';
import 'src/screens/notifications_screen.dart';
import 'src/screens/warehouse_screen.dart';
import 'src/theme.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  final state = AppState()..init();
  runApp(DroneDeliveryApp(state: state));
}

class DroneDeliveryApp extends StatelessWidget {
  const DroneDeliveryApp({super.key, required this.state});
  final AppState state;

  @override
  Widget build(BuildContext context) {
    return AppScope(
      state: state,
      child: MaterialApp(
        title: 'Drone Delivery',
        debugShowCheckedModeBanner: false,
        theme: buildTheme(Brightness.light),
        darkTheme: buildTheme(Brightness.dark),
        home: const RootShell(),
      ),
    );
  }
}

class RootShell extends StatefulWidget {
  const RootShell({super.key});

  @override
  State<RootShell> createState() => _RootShellState();
}

class _RootShellState extends State<RootShell> {
  int _index = 0;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => AppScope.read(context).requestNotificationPermissionOnce());
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final unread = app.unreadCount;
    return Scaffold(
      body: IndexedStack(
        index: _index,
        children: const [HomeScreen(), NotificationsScreen(), HistoryScreen(), WarehouseScreen()],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) {
          setState(() => _index = i);
          if (i == 1) app.markNotificationsRead();
          app.refreshAll();
        },
        destinations: [
          const NavigationDestination(
              icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home_rounded), label: 'Home'),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: unread > 0 && _index != 1,
              label: Text('$unread'),
              child: const Icon(Icons.notifications_outlined),
            ),
            selectedIcon: const Icon(Icons.notifications_rounded),
            label: 'Alerts',
          ),
          const NavigationDestination(
              icon: Icon(Icons.receipt_long_outlined), selectedIcon: Icon(Icons.receipt_long_rounded), label: 'History'),
          const NavigationDestination(
              icon: Icon(Icons.warehouse_outlined), selectedIcon: Icon(Icons.warehouse_rounded), label: 'Warehouse'),
        ],
      ),
    );
  }
}
