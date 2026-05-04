import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../models/robot_state.dart';
import '../services/mqtt_service.dart';

class ModeSelector extends StatelessWidget {
  const ModeSelector({super.key});

  @override
  Widget build(BuildContext context) {
    final robotState = context.watch<RobotState>();
    final mqtt       = context.read<MqttService>();
    final current    = robotState.mode;
    final isEstop    = current == RobotMode.estop;

    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _ModeBtn(
              label: 'MANUAL',
              icon: Icons.gamepad,
              active: current == RobotMode.manual,
              disabled: isEstop,
              onTap: () => mqtt.sendModeSet(RobotMode.manual),
            ),
            const SizedBox(width: 8),
            _ModeBtn(
              label: 'AUTO',
              icon: Icons.route,
              active: current == RobotMode.auto,
              disabled: isEstop,
              onTap: () => mqtt.sendModeSet(RobotMode.auto),
            ),
            const SizedBox(width: 8),
            _ModeBtn(
              label: 'FOLLOW',
              icon: Icons.directions_walk,
              active: current == RobotMode.follow,
              disabled: isEstop,
              onTap: () => mqtt.sendModeSet(RobotMode.follow),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModeBtn extends StatelessWidget {
  final String  label;
  final IconData icon;
  final bool    active;
  final bool    disabled;
  final VoidCallback onTap;

  const _ModeBtn({
    required this.label,
    required this.icon,
    required this.active,
    required this.disabled,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: (!disabled && !active) ? onTap : null,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: active
              ? Theme.of(context).colorScheme.primary
              : disabled
                  ? Colors.grey[200]
                  : Colors.grey[100],
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: active
                ? Theme.of(context).colorScheme.primary
                : Colors.grey[300]!,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              color: active ? Colors.white : (disabled ? Colors.grey[400] : Colors.grey[700]),
              size: 20,
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: active ? Colors.white : (disabled ? Colors.grey[400] : Colors.grey[700]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
