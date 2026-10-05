/// Small date/time helpers (no intl dependency needed).
library;

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const _days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

String formatTime(DateTime? t) {
  if (t == null) return '';
  final h = t.hour % 12 == 0 ? 12 : t.hour % 12;
  final m = t.minute.toString().padLeft(2, '0');
  return '$h:$m ${t.hour < 12 ? 'AM' : 'PM'}';
}

String formatDay(DateTime? t, {DateTime? now}) {
  if (t == null) return '';
  final today = DateTime((now ?? DateTime.now()).year, (now ?? DateTime.now()).month, (now ?? DateTime.now()).day);
  final day = DateTime(t.year, t.month, t.day);
  final diff = today.difference(day).inDays;
  if (diff == 0) return 'Today';
  if (diff == 1) return 'Yesterday';
  return '${_days[t.weekday - 1]}, ${t.day} ${_months[t.month - 1]}';
}

String formatDayTime(DateTime? t) => t == null ? '' : '${formatDay(t)}, ${formatTime(t)}';

String formatDuration(Duration d) {
  if (d.inSeconds < 60) return '${d.inSeconds} s';
  if (d.inMinutes < 60) return '${d.inMinutes} min';
  return '${d.inHours} h ${d.inMinutes % 60} min';
}

String formatAgo(DateTime? t) {
  if (t == null) return '';
  final d = DateTime.now().difference(t);
  if (d.inSeconds < 10) return 'just now';
  if (d.inSeconds < 60) return '${d.inSeconds} s ago';
  if (d.inMinutes < 60) return '${d.inMinutes} min ago';
  return formatDayTime(t);
}

/// Turns an event name such as "PACKAGE_RELEASED" into "Package released".
String humanize(String constant) {
  final s = constant.replaceAll('_', ' ').toLowerCase().replaceAll('rtl', 'RTL');
  return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}
