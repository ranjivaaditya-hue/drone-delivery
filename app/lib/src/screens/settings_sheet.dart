import 'package:flutter/material.dart';

import '../app_state.dart';
import '../tracking.dart';

Future<void> showSettingsSheet(BuildContext context) => showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      builder: (_) => const _SettingsSheet(),
    );

class _SettingsSheet extends StatefulWidget {
  const _SettingsSheet();

  @override
  State<_SettingsSheet> createState() => _SettingsSheetState();
}

class _SettingsSheetState extends State<_SettingsSheet> {
  late final _url = TextEditingController(text: AppScope.read(context).serverUrl ?? '');
  String? _message;
  bool _ok = false;
  bool _busy = false;
  bool? _notificationsAllowed;

  @override
  void initState() {
    super.initState();
    TrackingService.notificationsAllowed().then((v) {
      if (mounted) setState(() => _notificationsAllowed = v);
    });
  }

  @override
  void dispose() {
    _url.dispose();
    super.dispose();
  }

  Future<void> _run(Future<String?> Function() action, String okText) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    final err = await action();
    if (!mounted) return;
    setState(() {
      _busy = false;
      _ok = err == null;
      _message = err ?? okText;
    });
  }

  @override
  Widget build(BuildContext context) {
    final app = AppScope.read(context);
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 0, 20, 24 + MediaQuery.viewInsetsOf(context).bottom),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Delivery server', style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
        const SizedBox(height: 4),
        Text('The PC running the backend (python backend/app.py). It prints this address when it starts.',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: 16),
        TextField(
          controller: _url,
          keyboardType: TextInputType.url,
          autocorrect: false,
          decoration: const InputDecoration(
            labelText: 'Server address',
            hintText: '192.168.1.20:8000',
            prefixIcon: Icon(Icons.dns_outlined),
          ),
        ),
        if (_message != null) ...[
          const SizedBox(height: 10),
          Row(children: [
            Icon(_ok ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                size: 18, color: _ok ? const Color(0xFF16A34A) : scheme.error),
            const SizedBox(width: 8),
            Expanded(child: Text(_message!, style: TextStyle(color: _ok ? const Color(0xFF16A34A) : scheme.error))),
          ]),
        ],
        const SizedBox(height: 16),
        Row(children: [
          Expanded(
            child: OutlinedButton(
              onPressed: _busy ? null : () => _run(() => app.testServer(_url.text), 'Server reachable ✓'),
              style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              child: const Text('Test'),
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: FilledButton(
              onPressed: _busy
                  ? null
                  : () async {
                      await _run(() => app.setServerUrl(_url.text), 'Saved and connected ✓');
                      if (_ok && context.mounted) Navigator.pop(context);
                    },
              style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
              child: _busy
                  ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Text('Save'),
            ),
          ),
        ]),
        if (TrackingService.supported) ...[
          const Divider(height: 36),
          Row(children: [
            Icon(Icons.notifications_active_outlined, color: scheme.primary),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                _notificationsAllowed == null
                    ? 'Checking notification permission…'
                    : _notificationsAllowed!
                        ? 'Delivery notifications are on'
                        : 'Notifications are off: you will not get delivery alerts',
              ),
            ),
            if (_notificationsAllowed == false)
              TextButton(
                onPressed: () async {
                  final ok = await TrackingService.requestPermission();
                  if (mounted) setState(() => _notificationsAllowed = ok);
                },
                child: const Text('Allow'),
              ),
          ]),
        ],
      ]),
    );
  }
}
