import 'dart:async';

import 'package:flutter/material.dart';

import '../api.dart';
import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';
import '../widgets/timeline.dart';

/// Full status of one delivery: current state, timeline with times, and details.
class DeliveryStatusScreen extends StatefulWidget {
  const DeliveryStatusScreen({super.key, required this.deliveryId});
  final String deliveryId;

  @override
  State<DeliveryStatusScreen> createState() => _DeliveryStatusScreenState();
}

class _DeliveryStatusScreenState extends State<DeliveryStatusScreen> {
  Delivery? _delivery;
  String? _error;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final app = AppScope.read(context);
    // The current delivery is already polled by AppState, so reuse it when it matches.
    final cur = app.current;
    if (cur != null && cur.id == widget.deliveryId && app.error == null) {
      if (mounted) setState(() => (_delivery = cur, _error = null));
      return;
    }
    try {
      final d = await app.loadDelivery(widget.deliveryId);
      if (mounted) setState(() => (_delivery = d, _error = null));
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
    if (_delivery?.status.isTerminal ?? false) _timer?.cancel();
  }

  @override
  Widget build(BuildContext context) {
    AppScope.of(context); // rebuild when the polled state changes
    final d = _delivery;
    return Scaffold(
      appBar: AppBar(title: const Text('Delivery status')),
      body: d == null
          ? Center(child: _error == null ? const CircularProgressIndicator() : Text(_error!))
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
                children: [
                  _StatusHeader(delivery: d),
                  const SizedBox(height: 16),
                  SectionCard(title: 'Progress', child: DeliveryTimeline(delivery: d)),
                  const SizedBox(height: 16),
                  SectionCard(
                    title: 'Details',
                    child: Column(children: [
                      InfoRow(label: 'Package', value: d.packageId),
                      InfoRow(label: 'Customer', value: d.customerName),
                      InfoRow(label: 'Delivery ID', value: d.id),
                      InfoRow(label: 'Delivery status', value: '', valueWidget: deliveryStatusChip(d)),
                      if (d.createdAt != null) InfoRow(label: 'Ordered', value: formatDayTime(d.createdAt)),
                      if (d.timeOf(DeliveryStatus.departed) != null)
                        InfoRow(label: 'Took off', value: formatDayTime(d.timeOf(DeliveryStatus.departed))),
                      if (d.timeOf(DeliveryStatus.packageDelivered) != null)
                        InfoRow(label: 'Delivered', value: formatDayTime(d.timeOf(DeliveryStatus.packageDelivered))),
                      if (d.finishedAt != null) InfoRow(label: 'Finished', value: formatDayTime(d.finishedAt)),
                    ]),
                  ),
                ],
              ),
            ),
    );
  }
}

class _StatusHeader extends StatelessWidget {
  const _StatusHeader({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final style = statusStyle(delivery.status);
    final t = Theme.of(context).textTheme;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        gradient: LinearGradient(colors: style.gradient, begin: Alignment.topLeft, end: Alignment.bottomRight),
        borderRadius: BorderRadius.circular(24),
      ),
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.18), shape: BoxShape.circle),
          child: Icon(style.icon, color: Colors.white, size: 28),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('#${delivery.id}', style: t.labelLarge?.copyWith(color: Colors.white70, fontWeight: FontWeight.w700)),
            const SizedBox(height: 2),
            Text(delivery.headline,
                style: t.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w900, letterSpacing: 0.3)),
            const SizedBox(height: 2),
            Text(statusDescription(delivery.status), style: t.bodySmall?.copyWith(color: Colors.white.withValues(alpha: 0.9))),
          ]),
        ),
      ]),
    );
  }
}
