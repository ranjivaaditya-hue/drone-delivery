import 'package:flutter/material.dart';

import '../format.dart';
import '../models.dart';
import '../theme.dart';

enum _StepState { done, active, pending, skipped }

class _Step {
  const _Step(this.title, this.activeTitle, this.subtitle, this.timeState, this.doneAt, this.activeWhen);
  final String title;
  final String activeTitle;
  final String subtitle;
  final DeliveryStatus timeState; // whose timestamp is shown
  final DeliveryStatus doneAt; // step is done once the delivery reaches this state
  final Set<DeliveryStatus> activeWhen;
}

const _steps = [
  _Step('Order confirmed', 'Order confirmed', 'Your package is ready at the warehouse', DeliveryStatus.ready,
      DeliveryStatus.ready, {}),
  _Step('Drone took off', 'Preparing for takeoff', 'The drone has left the warehouse', DeliveryStatus.departed,
      DeliveryStatus.departed, {DeliveryStatus.ready}),
  _Step('Drone is on the way', 'Drone is on the way', 'Flying to the delivery location', DeliveryStatus.delivering,
      DeliveryStatus.packageDelivered, {DeliveryStatus.departed, DeliveryStatus.delivering}),
  _Step('Package delivered', 'Package delivered', 'Released at the delivery location',
      DeliveryStatus.packageDelivered, DeliveryStatus.packageDelivered, {}),
  _Step('Drone returned', 'Drone returning', 'Back at the warehouse', DeliveryStatus.completed,
      DeliveryStatus.completed, {DeliveryStatus.returningHome}),
];

/// Vertical progress timeline, styled like a food-delivery app's order tracker.
class DeliveryTimeline extends StatelessWidget {
  const DeliveryTimeline({super.key, required this.delivery, this.showTimes = true, this.showSubtitles = true});

  final Delivery delivery;
  final bool showTimes;
  final bool showSubtitles;

  @override
  Widget build(BuildContext context) {
    final cancelled = delivery.status == DeliveryStatus.cancelled;
    final reached = cancelled ? delivery.furthestReached : delivery.status;
    final states = [
      for (final step in _steps)
        if (reached.flowIndex >= step.doneAt.flowIndex)
          _StepState.done
        else if (!cancelled && step.activeWhen.contains(reached))
          _StepState.active
        else
          cancelled ? _StepState.skipped : _StepState.pending,
    ];
    return Column(
      children: [
        for (var i = 0; i < _steps.length; i++)
          _TimelineRow(
            step: _steps[i],
            state: states[i],
            time: showTimes ? delivery.timeOf(_steps[i].timeState) : null,
            showSubtitle: showSubtitles,
            isLast: i == _steps.length - 1,
            nextReached: i < _steps.length - 1 && states[i + 1] != _StepState.pending && states[i + 1] != _StepState.skipped,
          ),
        if (cancelled)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Row(children: [
              Icon(Icons.cancel_rounded, size: 18, color: Theme.of(context).colorScheme.error),
              const SizedBox(width: 8),
              Text('Delivery cancelled', style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ]),
          ),
      ],
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.step,
    required this.state,
    required this.time,
    required this.showSubtitle,
    required this.isLast,
    required this.nextReached,
  });

  final _Step step;
  final _StepState state;
  final DateTime? time;
  final bool showSubtitle;
  final bool isLast;
  final bool nextReached;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final muted = scheme.onSurfaceVariant.withValues(alpha: 0.55);
    final doneColor = success;
    final activeColor = scheme.primary;
    final title = state == _StepState.active ? step.activeTitle : step.title;
    final textStyle = Theme.of(context).textTheme.titleSmall?.copyWith(
          fontWeight: state == _StepState.pending || state == _StepState.skipped ? FontWeight.w500 : FontWeight.w700,
          color: state == _StepState.pending || state == _StepState.skipped ? muted : scheme.onSurface,
          decoration: state == _StepState.skipped ? TextDecoration.lineThrough : null,
        );
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            width: 28,
            child: Column(
              children: [
                _Marker(state: state, doneColor: doneColor, activeColor: activeColor, muted: muted),
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 3,
                      margin: const EdgeInsets.symmetric(vertical: 3),
                      decoration: BoxDecoration(
                        color: state == _StepState.done && nextReached
                            ? doneColor
                            : scheme.outlineVariant.withValues(alpha: 0.6),
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 18, top: 2),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(child: Text(title, style: textStyle)),
                    if (time != null && state == _StepState.done)
                      Text(formatTime(time), style: Theme.of(context).textTheme.labelMedium?.copyWith(color: muted)),
                    if (state == _StepState.active)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                        decoration: BoxDecoration(
                            color: activeColor.withValues(alpha: 0.12), borderRadius: BorderRadius.circular(20)),
                        child: Text('NOW',
                            style: TextStyle(fontSize: 10, fontWeight: FontWeight.w800, color: activeColor)),
                      ),
                  ]),
                  if (showSubtitle && state != _StepState.pending && state != _StepState.skipped)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text(step.subtitle,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant)),
                    ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Marker extends StatelessWidget {
  const _Marker({required this.state, required this.doneColor, required this.activeColor, required this.muted});
  final _StepState state;
  final Color doneColor;
  final Color activeColor;
  final Color muted;

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case _StepState.done:
        return Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(color: doneColor, shape: BoxShape.circle),
          child: const Icon(Icons.check_rounded, size: 16, color: Colors.white),
        );
      case _StepState.active:
        return _PulsingDot(color: activeColor);
      case _StepState.pending:
      case _StepState.skipped:
        return Container(
          width: 24,
          height: 24,
          decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: muted, width: 2.5)),
        );
    }
  }
}

class _PulsingDot extends StatefulWidget {
  const _PulsingDot({required this.color});
  final Color color;

  @override
  State<_PulsingDot> createState() => _PulsingDotState();
}

class _PulsingDotState extends State<_PulsingDot> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1400))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 24,
      height: 24,
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, _) => Stack(alignment: Alignment.center, children: [
          Container(
            width: 24 * (0.6 + 0.4 * _c.value),
            height: 24 * (0.6 + 0.4 * _c.value),
            decoration: BoxDecoration(
                color: widget.color.withValues(alpha: 0.35 * (1 - _c.value)), shape: BoxShape.circle),
          ),
          Container(
            width: 13,
            height: 13,
            decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
          ),
        ]),
      ),
    );
  }
}
