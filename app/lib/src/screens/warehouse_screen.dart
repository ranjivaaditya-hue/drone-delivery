import 'package:flutter/material.dart';

import '../api.dart';
import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../theme.dart';
import '../widgets/common.dart';

/// Simple operator view. It shows delivery state only: Mission Planner stays the place for telemetry.
class WarehouseScreen extends StatelessWidget {
  const WarehouseScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final d = app.current;
    final inFlight = d != null && d.isActive && d.status != DeliveryStatus.ready;
    return Scaffold(
      appBar: AppBar(title: const Text('Warehouse mode')),
      body: RefreshIndicator(
        onRefresh: app.refreshAll,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            _MonitorCard(bridge: app.bridge, configured: app.configured, error: app.error),
            const SizedBox(height: 14),
            SectionCard(
              title: 'Current mission',
              trailing: d == null ? null : deliveryStatusChip(d),
              child: d == null
                  ? const Text('No delivery prepared. Create one with "New delivery".')
                  : Column(children: [
                      InfoRow(label: 'Drone', value: d.droneId),
                      const InfoRow(label: 'Mission', value: 'DELIVERY'),
                      InfoRow(
                        label: 'Current state',
                        value: '',
                        valueWidget: Text(d.status.wire,
                            style: TextStyle(fontWeight: FontWeight.w900, color: statusStyle(d.status).accent)),
                      ),
                      InfoRow(label: 'Package', value: d.packageId),
                      InfoRow(label: 'Customer', value: d.customerName),
                      InfoRow(label: 'Delivery', value: d.id),
                    ]),
            ),
            const SizedBox(height: 14),
            FilledButton.icon(
              onPressed: inFlight || !app.configured ? null : () => _startDemo(context),
              icon: const Icon(Icons.play_arrow_rounded),
              label: const Text('Start demo mission'),
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
            ),
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: inFlight || !app.configured ? null : () => _newDelivery(context, d),
              icon: const Icon(Icons.add_box_outlined),
              label: Text(d?.status == DeliveryStatus.ready ? 'Edit delivery' : 'New delivery'),
              style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(50)),
            ),
            if (d != null && d.isActive)
              Align(
                alignment: Alignment.centerRight,
                child: TextButton.icon(
                  onPressed: () => _cancel(context, d),
                  icon: const Icon(Icons.block_rounded, size: 18),
                  label: const Text('Cancel / close delivery'),
                  style: TextButton.styleFrom(foregroundColor: Theme.of(context).colorScheme.error),
                ),
              ),
            const SizedBox(height: 8),
            if (d != null) SectionCard(title: 'Event log', child: _EventLog(delivery: d)),
          ],
        ),
      ),
    );
  }

  Future<void> _startDemo(BuildContext context) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final warning = await AppScope.read(context).startDemo();
      messenger.showSnackBar(SnackBar(
          content: Text(warning ?? 'Demo mission requested. The drone "takes off" in a few seconds.')));
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _cancel(BuildContext context, Delivery d) async {
    final delivered = d.status.flowIndex >= DeliveryStatus.packageDelivered.flowIndex;
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(delivered ? 'Close ${d.id}?' : 'Cancel ${d.id}?'),
        content: Text(delivered
            ? 'The package was already delivered. The delivery will be closed as COMPLETED.'
            : 'Use this only if the flight was aborted. The customer will see the delivery as cancelled.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(delivered ? 'Close' : 'Cancel delivery')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final messenger = ScaffoldMessenger.of(context);
    try {
      await AppScope.read(context).cancelCurrent();
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  Future<void> _newDelivery(BuildContext context, Delivery? current) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (_) => _NewDeliverySheet(editing: current?.status == DeliveryStatus.ready ? current : null),
    );
  }
}

class _MonitorCard extends StatelessWidget {
  const _MonitorCard({required this.bridge, required this.configured, required this.error});
  final BridgeStatus? bridge;
  final bool configured;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final b = bridge;
    final scheme = Theme.of(context).colorScheme;
    final (String label, Color color) = !configured || error != null
        ? ('Server unreachable', scheme.error)
        : b == null || !b.online
            ? ('Event monitor offline', const Color(0xFFD97706))
            : b.isDemo
                ? ('Online · Demo mode', const Color(0xFF7C3AED))
                : ('Online · Live MAVLink', success);
    return SectionCard(
      child: Row(children: [
        Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: color.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(14)),
          child: Icon(Icons.settings_input_antenna_rounded, color: color),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('PC event monitor', style: Theme.of(context).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 2),
            Text(
              b == null || !b.online
                  ? 'Start it on the PC: python pc_bridge/main.py${b?.isDemo ?? false ? ' --demo' : ''}'
                  : b.isDemo
                      ? 'Simulated events (no drone needed)'
                      : (b.vehicleConnected ? 'Drone link: receiving MAVLink' : 'Drone link: no heartbeat'),
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ]),
        ),
        StatusChip(label: label, color: color),
      ]),
    );
  }
}

class _EventLog extends StatelessWidget {
  const _EventLog({required this.delivery});
  final Delivery delivery;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final events = delivery.events.reversed.toList();
    return Column(children: [
      for (final e in events)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(
              width: 64,
              child: Text(formatTime(e.timestamp),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.onSurfaceVariant)),
            ),
            Expanded(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: 6, runSpacing: 4, crossAxisAlignment: WrapCrossAlignment.center, children: [
                  Text(humanize(e.event),
                      style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: e.isWarning ? const Color(0xFFB45309) : scheme.onSurface)),
                  if (e.state != null) StatusChip(label: e.state!.wire, color: statusStyle(e.state!).accent),
                  if (e.isWarning) const StatusChip(label: 'WARNING', color: Color(0xFFB45309)),
                ]),
                if (e.evidence.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 3),
                    child: Text('${e.source} · ${e.evidence}',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                  ),
              ]),
            ),
          ]),
        ),
    ]);
  }
}

class _NewDeliverySheet extends StatefulWidget {
  const _NewDeliverySheet({this.editing});
  final Delivery? editing;

  @override
  State<_NewDeliverySheet> createState() => _NewDeliverySheetState();
}

class _NewDeliverySheetState extends State<_NewDeliverySheet> {
  final _form = GlobalKey<FormState>();
  late final _package = TextEditingController(text: widget.editing?.packageId ?? '');
  late final _name = TextEditingController(text: widget.editing?.customerName ?? '');
  final _phone = TextEditingController();
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _package.dispose();
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await AppScope.read(context).createDelivery(
          packageId: _package.text.trim(), customerName: _name.text.trim(), customerPhone: _phone.text.trim());
      if (mounted) Navigator.pop(context);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 20 + MediaQuery.viewInsetsOf(context).bottom),
      child: Form(
        key: _form,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(widget.editing == null ? 'New delivery' : 'Edit ${widget.editing!.id}',
              style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 4),
          Text('Phone numbers are only used by the PC to send SMS; they are never shown in the app.',
              style: Theme.of(context).textTheme.bodySmall),
          const SizedBox(height: 16),
          TextFormField(
            controller: _package,
            decoration: const InputDecoration(labelText: 'Package ID', hintText: 'Leave empty for automatic (PKG-00N)'),
            textCapitalization: TextCapitalization.characters,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _name,
            decoration: const InputDecoration(labelText: 'Customer name'),
            textCapitalization: TextCapitalization.words,
            validator: (v) => (v == null || v.trim().isEmpty) && widget.editing == null ? 'Required' : null,
          ),
          const SizedBox(height: 12),
          TextFormField(
            controller: _phone,
            decoration: InputDecoration(
              labelText: 'Customer phone (for SMS)',
              hintText: widget.editing == null ? '+91XXXXXXXXXX' : 'Leave empty to keep the current number',
            ),
            keyboardType: TextInputType.phone,
            validator: (v) {
              final s = (v ?? '').replaceAll(' ', '');
              if (s.isEmpty) return widget.editing == null ? 'Required for the customer SMS' : null;
              return RegExp(r'^\+[1-9]\d{7,14}$').hasMatch(s) ? null : 'Use international format, e.g. +919876543210';
            },
          ),
          if (_error != null) ...[
            const SizedBox(height: 10),
            Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
          const SizedBox(height: 18),
          FilledButton(
            onPressed: _saving ? null : _save,
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(50)),
            child: _saving
                ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                : Text(widget.editing == null ? 'Create delivery' : 'Save'),
          ),
        ]),
      ),
    );
  }
}
