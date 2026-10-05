import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models.dart';
import '../theme.dart';

/// Animated illustration of the delivery state. It is not a map or a position:
/// the app never shows where the drone is, only what stage the delivery is in.
class DroneScene extends StatefulWidget {
  const DroneScene({super.key, required this.status, this.height = 150});

  final DeliveryStatus status;
  final double height;

  @override
  State<DroneScene> createState() => _DroneSceneState();
}

class _DroneSceneState extends State<DroneScene> with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1600))
    ..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.status;
    final returning = s == DeliveryStatus.returningHome;
    return SizedBox(
      height: widget.height,
      child: Stack(
        children: [
          Positioned.fill(
            child: AnimatedBuilder(
              animation: _c,
              builder: (_, _) => CustomPaint(painter: _DronePainter(_c.value, s)),
            ),
          ),
          Positioned(
            left: 4,
            bottom: 0,
            child: _GroundIcon(icon: Icons.warehouse_rounded, highlight: returning || s == DeliveryStatus.completed),
          ),
          Positioned(
            right: 4,
            bottom: 0,
            child: _GroundIcon(
                icon: Icons.location_on_rounded,
                highlight: s == DeliveryStatus.delivering || s == DeliveryStatus.packageDelivered),
          ),
        ],
      ),
    );
  }
}

class _GroundIcon extends StatelessWidget {
  const _GroundIcon({required this.icon, required this.highlight});
  final IconData icon;
  final bool highlight;

  @override
  Widget build(BuildContext context) => Icon(icon, size: 22, color: Colors.white.withValues(alpha: highlight ? 0.95 : 0.45));
}

class _DronePainter extends CustomPainter {
  _DronePainter(this.t, this.status);

  final double t; // 0..1 animation phase
  final DeliveryStatus status;

  @override
  void paint(Canvas canvas, Size size) {
    final white = Colors.white;
    final groundY = size.height - 12;
    final cx = size.width / 2;
    final s = (size.height / 150).clamp(0.6, 1.4);
    final flying = status.isFlying || status == DeliveryStatus.packageDelivered;
    final landed = !flying;
    final bob = flying ? math.sin(t * 2 * math.pi) * 4 * s : 0.0;
    final cy = landed ? groundY - 21 * s : size.height * 0.36 + bob;
    final dir = status == DeliveryStatus.returningHome ? -1.0 : 1.0;

    // Ground line
    final ground = Paint()
      ..color = white.withValues(alpha: 0.28)
      ..strokeWidth = 2
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(Offset(34, groundY), Offset(size.width - 34, groundY), ground);

    // Landing pad under a landed drone
    if (landed) {
      canvas.drawOval(Rect.fromCenter(center: Offset(cx, groundY), width: 110 * s, height: 12 * s),
          Paint()..color = white.withValues(alpha: 0.18));
    }

    // Shadow under a flying drone
    if (flying) {
      final shadowW = 70 * s * (1 - bob / (30 * s));
      canvas.drawOval(Rect.fromCenter(center: Offset(cx, groundY), width: shadowW, height: 7 * s),
          Paint()..color = Colors.black.withValues(alpha: 0.12));
    }

    // Speed lines (direction of travel) while en route or returning
    if (status == DeliveryStatus.departed || status == DeliveryStatus.delivering || status == DeliveryStatus.returningHome) {
      final p = Paint()
        ..strokeWidth = 2.5 * s
        ..strokeCap = StrokeCap.round;
      for (var i = 0; i < 3; i++) {
        final phase = (t + i / 3) % 1.0;
        final len = 22 * s;
        final x0 = cx - dir * (78 * s + phase * 40 * s);
        final y = cy - 8 * s + i * 9 * s;
        p.color = white.withValues(alpha: 0.55 * (1 - phase));
        canvas.drawLine(Offset(x0, y), Offset(x0 - dir * len, y), p);
      }
    }

    // Package: hanging under the drone before the drop, on the ground after it
    final hasPackage = status.flowIndex <= DeliveryStatus.delivering.flowIndex;
    if (hasPackage) {
      final top = cy + 8 * s;
      final boxY = landed ? groundY - 9 * s : cy + 31 * s;
      if (!landed) {
        canvas.drawLine(Offset(cx, top), Offset(cx, boxY - 9 * s),
            Paint()
              ..color = white.withValues(alpha: 0.85)
              ..strokeWidth = 1.6 * s);
      }
      if (!landed) _drawBox(canvas, Offset(cx, boxY), s);
    }
    if (status == DeliveryStatus.packageDelivered) {
      final boxC = Offset(cx + 6 * s, groundY - 9 * s);
      _drawBox(canvas, boxC, s);
      _drawCheck(canvas, boxC + Offset(14 * s, -12 * s), 7 * s);
    }

    _drawDrone(canvas, Offset(cx, cy), s, landed ? 0.0 : t, landed && status != DeliveryStatus.ready);
    if (status == DeliveryStatus.ready) _drawBox(canvas, Offset(cx + 70 * s, groundY - 9 * s), s);
    if (status == DeliveryStatus.completed) _drawCheck(canvas, Offset(cx + 46 * s, cy - 26 * s), 9 * s);
  }

  void _drawDrone(Canvas canvas, Offset c, double s, double phase, bool idle) {
    final white = Paint()..color = Colors.white;
    final arm = Paint()
      ..color = Colors.white
      ..strokeWidth = 4 * s
      ..strokeCap = StrokeCap.round;

    // Arms and motor posts
    for (final side in [-1.0, 1.0]) {
      final end = Offset(c.dx + side * 44 * s, c.dy - 7 * s);
      canvas.drawLine(Offset(c.dx + side * 20 * s, c.dy - 2 * s), end, arm);
      canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromCenter(center: end + Offset(0, -3 * s), width: 6 * s, height: 8 * s),
              Radius.circular(2 * s)),
          white);
      // Rotor: blurred disc plus a blade whose apparent width follows the spin
      final hub = end + Offset(0, -8 * s);
      canvas.drawOval(Rect.fromCenter(center: hub, width: 42 * s, height: 5 * s),
          Paint()..color = Colors.white.withValues(alpha: idle ? 0.0 : 0.30));
      final blade = 42 * s * (idle ? 1.0 : math.cos((phase * 8 + (side > 0 ? 0.25 : 0)) * math.pi).abs());
      canvas.drawRRect(
          RRect.fromRectAndRadius(Rect.fromCenter(center: hub, width: math.max(blade, 6 * s), height: 3 * s),
              Radius.circular(2 * s)),
          Paint()..color = Colors.white.withValues(alpha: 0.95));
    }

    // Legs
    final leg = Paint()
      ..color = Colors.white
      ..strokeWidth = 3 * s
      ..strokeCap = StrokeCap.round;
    for (final side in [-1.0, 1.0]) {
      canvas.drawLine(Offset(c.dx + side * 12 * s, c.dy + 6 * s), Offset(c.dx + side * 18 * s, c.dy + 19 * s), leg);
      canvas.drawLine(Offset(c.dx + side * 13 * s, c.dy + 19 * s), Offset(c.dx + side * 24 * s, c.dy + 19 * s), leg);
    }

    // Body, canopy and camera
    canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromCenter(center: c, width: 54 * s, height: 17 * s), Radius.circular(9 * s)),
        white);
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromCenter(center: c + Offset(0, -9 * s), width: 26 * s, height: 9 * s), Radius.circular(5 * s)),
        white);
    canvas.drawCircle(c + Offset(0, 1 * s), 3.2 * s, Paint()..color = brandSeed.withValues(alpha: 0.85));
  }

  void _drawBox(Canvas canvas, Offset c, double s) {
    final rect = Rect.fromCenter(center: c, width: 24 * s, height: 18 * s);
    canvas.drawRRect(RRect.fromRectAndRadius(rect, Radius.circular(3 * s)), Paint()..color = amber);
    canvas.drawLine(Offset(c.dx, rect.top), Offset(c.dx, rect.bottom),
        Paint()
          ..color = const Color(0xFFB45309)
          ..strokeWidth = 2.4 * s);
  }

  void _drawCheck(Canvas canvas, Offset c, double r) {
    canvas.drawCircle(c, r, Paint()..color = Colors.white);
    final path = Path()
      ..moveTo(c.dx - r * 0.45, c.dy + r * 0.02)
      ..lineTo(c.dx - r * 0.1, c.dy + r * 0.38)
      ..lineTo(c.dx + r * 0.5, c.dy - r * 0.35);
    canvas.drawPath(
        path,
        Paint()
          ..color = success
          ..style = PaintingStyle.stroke
          ..strokeWidth = r * 0.28
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round);
  }

  @override
  bool shouldRepaint(_DronePainter old) => old.t != t || old.status != status;
}
