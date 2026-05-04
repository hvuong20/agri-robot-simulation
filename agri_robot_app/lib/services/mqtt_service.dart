import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:mqtt_client/mqtt_client.dart';
import 'package:mqtt_client/mqtt_server_client.dart';

import '../models/robot_state.dart';

/// MQTT topics
const _kTopicPosition     = 'robot/position';
const _kTopicStatus       = 'robot/status';
const _kTopicPath         = 'robot/path';
const _kTopicAlert        = 'robot/alert';
const _kTopicAppCommand   = 'app/command';
const _kTopicAppEstop     = 'app/estop';
const _kTopicAppBoundary  = 'app/boundary';
const _kTopicFollowPos    = 'app/follow_position';
const _kTopicCovConfig    = 'app/coverage_config';

/// Called when robot/alert arrives (e.g. stuck confirmed).
typedef AlertCallback = void Function(String alertType);

class MqttService extends ChangeNotifier {
  MqttServerClient? _client;
  bool _connected = false;
  Timer? _reconnectTimer;
  AlertCallback? onAlert;

  String brokerHost;
  int    brokerPort;
  final RobotState robotState;

  MqttService({
    required this.brokerHost,
    required this.brokerPort,
    required this.robotState,
  });

  bool get isConnected => _connected;

  // ── Connection ─────────────────────────────────────────────────────────────

  Future<void> connect() async {
    _client = MqttServerClient.withPort(brokerHost, 'agri_app_flutter', brokerPort);
    _client!.keepAlivePeriod = 60;
    _client!.autoReconnect   = true;
    _client!.logging(on: false);

    _client!.onConnected    = _onConnected;
    _client!.onDisconnected = _onDisconnected;
    _client!.onAutoReconnect = () => debugPrint('MQTT auto-reconnect...');

    final connMsg = MqttConnectMessage()
        .withClientIdentifier('agri_app_flutter')
        .startClean()
        .withWillQos(MqttQos.atLeastOnce);
    _client!.connectionMessage = connMsg;

    try {
      await _client!.connect();
    } catch (e) {
      debugPrint('MQTT connect error: $e');
      _scheduleReconnect();
      return;
    }

    if (_client!.connectionStatus!.state == MqttConnectionState.connected) {
      _onConnected();
    } else {
      _scheduleReconnect();
    }
  }

  void disconnect() {
    _reconnectTimer?.cancel();
    _client?.disconnect();
  }

  void _onConnected() {
    _connected = true;
    robotState.setMqttConnected(true);
    notifyListeners();
    debugPrint('MQTT connected to $brokerHost:$brokerPort');

    _subscribe(_kTopicPosition,  MqttQos.atMostOnce);
    _subscribe(_kTopicStatus,    MqttQos.atLeastOnce);
    _subscribe(_kTopicPath,      MqttQos.atMostOnce);
    _subscribe(_kTopicAlert,     MqttQos.atLeastOnce);

    _client!.updates!.listen(_onMessage);
  }

  void _onDisconnected() {
    _connected = false;
    robotState.setMqttConnected(false);
    notifyListeners();
    debugPrint('MQTT disconnected');
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 5), () {
      if (!_connected) connect();
    });
  }

  // ── Subscribe / receive ────────────────────────────────────────────────────

  void _subscribe(String topic, MqttQos qos) {
    _client?.subscribe(topic, qos);
  }

  void _onMessage(List<MqttReceivedMessage<MqttMessage>> events) {
    for (final event in events) {
      final topic   = event.topic;
      final payload = MqttPublishPayload.bytesToStringAsString(
        (event.payload as MqttPublishMessage).payload.message,
      );

      try {
        final data = jsonDecode(payload);
        if (topic == _kTopicPosition && data is Map<String, dynamic>) {
          robotState.updateFromPosition(data);
        } else if (topic == _kTopicStatus && data is Map<String, dynamic>) {
          robotState.updateFromStatus(data);
        } else if (topic == _kTopicPath && data is List) {
          robotState.updateCoveragePath(data);
        } else if (topic == _kTopicAlert && data is Map<String, dynamic>) {
          final alertType = data['type'] as String? ?? 'unknown';
          onAlert?.call(alertType);
        }
      } catch (e) {
        debugPrint('MQTT parse error [$topic]: $e');
      }
    }
  }

  // ── Publish helpers ────────────────────────────────────────────────────────

  void _publish(String topic, String payload, {MqttQos qos = MqttQos.atMostOnce}) {
    if (!_connected || _client == null) return;
    final builder = MqttClientPayloadBuilder()..addString(payload);
    _client!.publishMessage(topic, qos, builder.payload!);
  }

  void sendEstop() {
    _publish(_kTopicAppEstop, '{}', qos: MqttQos.exactlyOnce);
    debugPrint('MQTT ESTOP sent');
  }

  void sendEstopClear() {
    _publish(
      _kTopicAppCommand,
      jsonEncode({'type': 'estop_clear'}),
      qos: MqttQos.atLeastOnce,
    );
  }

  void sendModeSet(RobotMode mode) {
    _publish(
      _kTopicAppCommand,
      jsonEncode({'type': 'mode_set', 'mode': modeToString(mode)}),
      qos: MqttQos.atLeastOnce,
    );
  }

  void sendBoundary(String boundaryJson) {
    _publish(_kTopicAppBoundary, boundaryJson, qos: MqttQos.atLeastOnce);
  }

  void sendFollowPosition(double lat, double lon) {
    _publish(
      _kTopicFollowPos,
      jsonEncode({'lat': lat, 'lon': lon}),
      qos: MqttQos.atMostOnce,
    );
  }

  void sendCoverageConfig(double rowOffsetM) {
    _publish(
      _kTopicCovConfig,
      jsonEncode({'row_offset': rowOffsetM}),
      qos: MqttQos.atLeastOnce,
    );
  }
}
