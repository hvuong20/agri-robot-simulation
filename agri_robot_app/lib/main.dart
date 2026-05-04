import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models/robot_state.dart';
import 'screens/map_screen.dart';
import 'services/mqtt_service.dart';
import 'services/location_service.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final prefs = await SharedPreferences.getInstance();
  final host  = prefs.getString('mqtt_host') ?? '192.168.1.105';
  final port  = prefs.getInt('mqtt_port')    ?? 1883;

  final robotState      = RobotState();
  final locationService = LocationService();
  final mqttService     = MqttService(
    brokerHost: host,
    brokerPort: port,
    robotState: robotState,
  );

  // Connect in background — UI renders immediately with "disconnected" state
  mqttService.connect();

  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: robotState),
        ChangeNotifierProvider.value(value: mqttService),
        Provider.value(value: locationService),
      ],
      child: const AgriRobotApp(),
    ),
  );
}

class AgriRobotApp extends StatelessWidget {
  const AgriRobotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Agri Robot',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2E7D32), // farm green
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          centerTitle: false,
          elevation: 0,
        ),
      ),
      home: const MapScreen(),
    );
  }
}
