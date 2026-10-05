import 'package:flutter/material.dart';

import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'home_screen.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final items = app.history;
    return Scaffold(
      appBar: AppBar(title: const Text('Delivery history')),
      body: RefreshIndicator(
        onRefresh: app.refreshAll,
        child: items.isEmpty
            ? ListView(children: const [
                EmptyState(
                  icon: Icons.receipt_long_outlined,
                  title: 'No past deliveries',
                  message: 'Completed deliveries will be listed here.',
                ),
              ])
            : ListView.separated(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                itemCount: items.length,
                separatorBuilder: (_, _) => const SizedBox(height: 10),
                itemBuilder: (context, i) => _HistoryCard(items[i]),
              ),
      ),
    );
  }
}

class _HistoryCard extends StatelessWidget {
  const _HistoryCard(this.d);
  final Delivery d;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final style = statusStyle(d.status);
    final start = d.timeOf(DeliveryStatus.departed);
    final end = d.finishedAt;
    final flight = start != null && end != null ? formatDuration(end.difference(start)) : null;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: () => openDeliveryStatus(context, d.id),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: style.accent.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
              child: Icon(style.icon, color: style.accent),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${d.id} · ${d.packageId}',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
                const SizedBox(height: 3),
                Text('${d.customerName} · ${formatDayTime(end ?? d.createdAt)}',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                if (flight != null) ...[
                  const SizedBox(height: 3),
                  Text('Flight time $flight',
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
                ],
              ]),
            ),
            deliveryStatusChip(d),
          ]),
        ),
      ),
    );
  }
}
