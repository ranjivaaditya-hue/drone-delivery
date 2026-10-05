import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';
import 'drone_scene.dart';

/// White rounded card with an optional title row.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, this.title, this.trailing, required this.child, this.padding});

  final String? title;
  final Widget? trailing;
  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: padding ?? const EdgeInsets.fromLTRB(18, 16, 18, 18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (title != null) ...[
              Row(children: [
                Expanded(
                  child: Text(title!,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
                ),
                ?trailing,
              ]),
              const SizedBox(height: 14),
            ],
            child,
          ],
        ),
      ),
    );
  }
}

class StatusChip extends StatelessWidget {
  const StatusChip({super.key, required this.label, required this.color, this.icon});
  final String label;
  final Color color;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.13), borderRadius: BorderRadius.circular(30)),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        if (icon != null) ...[Icon(icon, size: 14, color: color), const SizedBox(width: 5)],
        Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w700, fontSize: 12)),
      ]),
    );
  }
}

StatusChip deliveryStatusChip(Delivery d) {
  final style = statusStyle(d.status);
  return StatusChip(label: d.summary.isEmpty ? d.status.label : d.summary, color: style.accent, icon: style.icon);
}

/// Label/value pair used in detail cards.
class InfoRow extends StatelessWidget {
  const InfoRow({super.key, required this.label, required this.value, this.valueWidget});
  final String label;
  final String value;
  final Widget? valueWidget;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(children: [
        Expanded(child: Text(label, style: t.bodyMedium?.copyWith(color: Theme.of(context).colorScheme.onSurfaceVariant))),
        valueWidget ?? Text(value, style: t.bodyMedium?.copyWith(fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

/// Small stacked label/value tile ("Package / PKG-001").
class InfoTile extends StatelessWidget {
  const InfoTile({super.key, required this.icon, required this.label, required this.value});
  final IconData icon;
  final String label;
  final Widget value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, color: scheme.primary, size: 22),
          const SizedBox(height: 10),
          Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: scheme.onSurfaceVariant)),
          const SizedBox(height: 4),
          DefaultTextStyle.merge(style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 16), child: value),
        ]),
      ),
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({super.key, required this.icon, required this.title, required this.message, this.action});
  final IconData icon;
  final String title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 48),
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(color: scheme.primaryContainer, shape: BoxShape.circle),
          child: Icon(icon, size: 36, color: scheme.onPrimaryContainer),
        ),
        const SizedBox(height: 18),
        Text(title,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 6),
        Text(message,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onSurfaceVariant)),
        if (action != null) ...[const SizedBox(height: 18), action!],
      ]),
    );
  }
}

/// Gradient hero card with the animated drone. This is the main visual: there is no map.
class DeliveryHeroCard extends StatelessWidget {
  const DeliveryHeroCard({super.key, required this.delivery, this.onTap, this.sceneHeight = 150});

  final Delivery delivery;
  final VoidCallback? onTap;
  final double sceneHeight;

  static int stepOf(DeliveryStatus s) => switch (s) {
        DeliveryStatus.ready => 1,
        DeliveryStatus.departed => 2,
        DeliveryStatus.delivering => 3,
        DeliveryStatus.packageDelivered => 4,
        DeliveryStatus.returningHome => 4,
        DeliveryStatus.completed => 5,
        _ => 0,
      };

  @override
  Widget build(BuildContext context) {
    final style = statusStyle(delivery.status);
    final t = Theme.of(context).textTheme;
    final step = stepOf(delivery.status);
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(28),
        child: Ink(
          decoration: BoxDecoration(
            gradient: LinearGradient(colors: style.gradient, begin: Alignment.topLeft, end: Alignment.bottomRight),
            borderRadius: BorderRadius.circular(28),
            boxShadow: [BoxShadow(color: style.accent.withValues(alpha: 0.35), blurRadius: 24, offset: const Offset(0, 10))],
          ),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 20),
            child: Column(children: [
              Row(children: [
                const Icon(Icons.inventory_2_rounded, size: 16, color: Colors.white70),
                const SizedBox(width: 8),
                Text('MY DELIVERY',
                    style: t.labelLarge?.copyWith(color: Colors.white70, letterSpacing: 1.6, fontWeight: FontWeight.w700)),
                const Spacer(),
                if (delivery.isActive) const _LiveBadge(),
              ]),
              const SizedBox(height: 4),
              Align(
                alignment: Alignment.centerLeft,
                child: Text('#${delivery.id}',
                    style: t.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w800)),
              ),
              const SizedBox(height: 6),
              DroneScene(status: delivery.status, height: sceneHeight),
              const SizedBox(height: 12),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 400),
                child: Text(
                  delivery.headline,
                  key: ValueKey(delivery.headline),
                  textAlign: TextAlign.center,
                  style: t.headlineSmall?.copyWith(color: Colors.white, fontWeight: FontWeight.w900, letterSpacing: 0.4),
                ),
              ),
              const SizedBox(height: 6),
              Text(statusDescription(delivery.status),
                  textAlign: TextAlign.center, style: t.bodyMedium?.copyWith(color: Colors.white.withValues(alpha: 0.9))),
              if (step > 0) ...[
                const SizedBox(height: 16),
                Row(children: [
                  for (var i = 1; i <= 5; i++)
                    Expanded(
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 500),
                        height: 6,
                        margin: EdgeInsets.only(right: i < 5 ? 5 : 0),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: i <= step ? 0.95 : 0.25),
                          borderRadius: BorderRadius.circular(4),
                        ),
                      ),
                    ),
                ]),
              ],
            ]),
          ),
        ),
      ),
    );
  }
}

class _LiveBadge extends StatelessWidget {
  const _LiveBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), borderRadius: BorderRadius.circular(20)),
      child: const Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(Icons.circle, size: 8, color: Color(0xFF4ADE80)),
        SizedBox(width: 6),
        Text('LIVE', style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800, letterSpacing: 1)),
      ]),
    );
  }
}
