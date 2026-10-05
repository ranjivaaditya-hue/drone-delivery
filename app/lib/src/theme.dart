import 'package:flutter/material.dart';

import 'models.dart';

const brandSeed = Color(0xFF4F46E5);
const amber = Color(0xFFFBBF24);
const success = Color(0xFF10B981);

ThemeData buildTheme(Brightness brightness) {
  final scheme = ColorScheme.fromSeed(seedColor: brandSeed, brightness: brightness);
  final light = brightness == Brightness.light;
  final base = ThemeData(colorScheme: scheme, useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: light ? const Color(0xFFF4F5FB) : scheme.surface,
    appBarTheme: AppBarTheme(
      backgroundColor: light ? const Color(0xFFF4F5FB) : scheme.surface,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: base.textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800, color: scheme.onSurface),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      margin: EdgeInsets.zero,
      color: light ? Colors.white : scheme.surfaceContainerHigh,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: light ? Colors.white : scheme.surfaceContainer,
      indicatorColor: scheme.primaryContainer,
      elevation: 2,
      height: 68,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: light ? const Color(0xFFF4F5FB) : scheme.surfaceContainerHighest,
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(14), borderSide: BorderSide.none),
    ),
  );
}

/// Visual identity of each delivery state.
class StatusStyle {
  const StatusStyle(this.gradient, this.accent, this.icon);
  final List<Color> gradient;
  final Color accent;
  final IconData icon;
}

StatusStyle statusStyle(DeliveryStatus s) => switch (s) {
      DeliveryStatus.ready => const StatusStyle(
          [Color(0xFF312E81), Color(0xFF4F46E5)], Color(0xFF4F46E5), Icons.inventory_2_rounded),
      DeliveryStatus.departed || DeliveryStatus.delivering => const StatusStyle(
          [Color(0xFF4338CA), Color(0xFF7C3AED)], Color(0xFF6D28D9), Icons.flight_takeoff_rounded),
      DeliveryStatus.packageDelivered || DeliveryStatus.returningHome => const StatusStyle(
          [Color(0xFF0F766E), Color(0xFF10B981)], Color(0xFF0D9488), Icons.where_to_vote_rounded),
      DeliveryStatus.completed => const StatusStyle(
          [Color(0xFF047857), Color(0xFF059669)], Color(0xFF059669), Icons.check_circle_rounded),
      DeliveryStatus.cancelled || DeliveryStatus.unknown => const StatusStyle(
          [Color(0xFF475569), Color(0xFF64748B)], Color(0xFF64748B), Icons.cancel_rounded),
    };

/// Customer-facing description under the headline.
String statusDescription(DeliveryStatus s) => switch (s) {
      DeliveryStatus.ready => 'Your delivery is being prepared.',
      DeliveryStatus.departed => 'Your delivery drone has taken off.',
      DeliveryStatus.delivering => 'Your package is being delivered by an autonomous drone.',
      DeliveryStatus.packageDelivered => 'Your package has been delivered.',
      DeliveryStatus.returningHome => 'Delivery completed. The drone is returning to the warehouse.',
      DeliveryStatus.completed => 'Delivery completed successfully.',
      DeliveryStatus.cancelled => 'This delivery was cancelled by the warehouse.',
      DeliveryStatus.unknown => '',
    };
