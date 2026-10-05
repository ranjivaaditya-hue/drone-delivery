import 'package:flutter/material.dart';

import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

class NotificationsScreen extends StatelessWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final items = app.notifications;
    final children = <Widget>[];
    String? day;
    for (final n in items) {
      final label = formatDay(n.timestamp);
      if (label != day) {
        day = label;
        children.add(Padding(
          padding: const EdgeInsets.fromLTRB(4, 14, 4, 8),
          child: Text(label.toUpperCase(),
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  letterSpacing: 1.2, fontWeight: FontWeight.w800, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        ));
      }
      children.add(Padding(padding: const EdgeInsets.only(bottom: 10), child: _NotificationTile(n)));
    }
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: RefreshIndicator(
        onRefresh: app.refreshAll,
        child: items.isEmpty
            ? ListView(children: const [
                EmptyState(
                  icon: Icons.notifications_none_rounded,
                  title: 'No notifications yet',
                  message: 'Updates such as "Drone has taken off" and "Package delivered" will show up here.',
                ),
              ])
            : ListView(padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: children),
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  const _NotificationTile(this.n);
  final AppNotification n;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final style = statusStyle(n.state);
    // Titles start with an emoji ("🚁 Drone has taken off"). Show it as the avatar.
    final space = n.title.indexOf(' ');
    final hasEmoji = space > 0 && n.title.runes.first > 0x2000;
    final emoji = hasEmoji ? n.title.substring(0, space) : null;
    final title = hasEmoji ? n.title.substring(space + 1) : n.title;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Container(
            width: 44,
            height: 44,
            alignment: Alignment.center,
            decoration: BoxDecoration(color: style.accent.withValues(alpha: 0.12), shape: BoxShape.circle),
            child: emoji != null
                ? Text(emoji, style: const TextStyle(fontSize: 20))
                : Icon(style.icon, color: style.accent, size: 22),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(
                  child: Text(title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                ),
                Text(formatTime(n.timestamp),
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
              ]),
              const SizedBox(height: 3),
              Text(n.body, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
              const SizedBox(height: 6),
              Text('${n.deliveryId} · ${n.packageId}',
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.primary, fontWeight: FontWeight.w700)),
            ]),
          ),
        ]),
      ),
    );
  }
}
