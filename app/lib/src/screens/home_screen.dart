import 'package:flutter/material.dart';

import '../app_state.dart';
import '../format.dart';
import '../models.dart';
import '../widgets/common.dart';
import '../widgets/timeline.dart';
import 'delivery_status_screen.dart';
import 'settings_sheet.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final app = AppScope.of(context);
    final d = app.current;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Drone Delivery'),
        actions: [
          if (app.configured) _ConnectionDot(connected: app.connected),
          IconButton(
            tooltip: 'Server settings',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => showSettingsSheet(context),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: app.refreshAll,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
          children: [
            if (!app.configured)
              _SetupCard(onSetup: () => showSettingsSheet(context))
            else if (app.loading && d == null)
              const Padding(padding: EdgeInsets.all(64), child: Center(child: CircularProgressIndicator()))
            else if (d == null && app.error != null)
              _OfflineCard(message: app.error!, url: app.serverUrl!, onSettings: () => showSettingsSheet(context))
            else if (d == null)
              const EmptyState(
                icon: Icons.inventory_2_outlined,
                title: 'No deliveries yet',
                message: 'Your delivery will appear here as soon as the warehouse prepares it.',
              )
            else ...[
              if (app.error != null) _StaleBanner(message: app.error!, lastUpdated: app.lastUpdated),
              DeliveryHeroCard(delivery: d, onTap: () => openDeliveryStatus(context, d.id)),
              const SizedBox(height: 16),
              SectionCard(
                title: 'Delivery progress',
                trailing: Text(formatAgo(app.lastUpdated),
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        )),
                child: DeliveryTimeline(delivery: d, showSubtitles: false),
              ),
              const SizedBox(height: 16),
              Row(children: [
                Expanded(child: InfoTile(icon: Icons.inventory_2_outlined, label: 'Package', value: Text(d.packageId))),
                const SizedBox(width: 12),
                Expanded(
                  child: InfoTile(
                    icon: Icons.local_shipping_outlined,
                    label: 'Delivery status',
                    value: Text(d.summary.isEmpty ? d.status.label : d.summary),
                  ),
                ),
              ]),
              const SizedBox(height: 16),
              OutlinedButton.icon(
                onPressed: () => openDeliveryStatus(context, d.id),
                icon: const Icon(Icons.timeline_rounded),
                label: const Text('View delivery details'),
                style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ConnectionDot extends StatelessWidget {
  const _ConnectionDot({required this.connected});
  final bool connected;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: connected ? 'Connected to the delivery server' : 'Not connected',
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6),
        child: Icon(Icons.circle, size: 10, color: connected ? const Color(0xFF22C55E) : const Color(0xFFF59E0B)),
      ),
    );
  }
}

class _SetupCard extends StatelessWidget {
  const _SetupCard({required this.onSetup});
  final VoidCallback onSetup;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: EmptyState(
        icon: Icons.wifi_tethering_rounded,
        title: 'Connect to the delivery server',
        message: "Enter the address of the PC running the delivery backend, e.g. 192.168.1.20:8000. "
            'The phone and the PC must be on the same Wi-Fi.',
        action: FilledButton.icon(onPressed: onSetup, icon: const Icon(Icons.link_rounded), label: const Text('Set server address')),
      ),
    );
  }
}

class _OfflineCard extends StatelessWidget {
  const _OfflineCard({required this.message, required this.url, required this.onSettings});
  final String message;
  final String url;
  final VoidCallback onSettings;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: EmptyState(
        icon: Icons.cloud_off_rounded,
        title: message,
        message: 'Trying $url every few seconds. Check that the backend is running on the PC, '
            'that the phone is on the same Wi-Fi, and that Windows Firewall allows port 8000.',
        action: OutlinedButton(onPressed: onSettings, child: const Text('Change server address')),
      ),
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.message, required this.lastUpdated});
  final String message;
  final DateTime? lastUpdated;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(color: scheme.errorContainer, borderRadius: BorderRadius.circular(14)),
      child: Row(children: [
        Icon(Icons.wifi_off_rounded, size: 18, color: scheme.onErrorContainer),
        const SizedBox(width: 10),
        Expanded(
          child: Text('$message Showing the last known status (${formatAgo(lastUpdated)}).',
              style: TextStyle(color: scheme.onErrorContainer, fontSize: 13)),
        ),
      ]),
    );
  }
}

void openDeliveryStatus(BuildContext context, String deliveryId) {
  Navigator.of(context).push(MaterialPageRoute(builder: (_) => DeliveryStatusScreen(deliveryId: deliveryId)));
}

/// Status of [DeliveryStatus] for screens that only need a label.
String statusLabel(Delivery d) => d.summary.isEmpty ? d.status.label : d.summary;
