import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'models/robot_state.dart';
import 'screens/map_screen.dart';
import 'screens/control_screen.dart';
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
          seedColor: const Color(0xFF2E7D32),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          centerTitle: false,
          elevation: 0,
        ),
      ),
      home: const _AppShell(),
    );
  }
}

/// Bottom-nav shell with Map and Control tabs.
/// Also registers the stuck alert callback so it shows a SnackBar from anywhere.
class _AppShell extends StatefulWidget {
  const _AppShell();

  @override
  State<_AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<_AppShell> {
  int _selectedIndex = 0;

  final _pages = const [
    MapScreen(),
    ControlScreen(),
  ];

  @override
  void initState() {
    super.initState();
    // Register stuck alert callback after first frame (context available)
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<MqttService>().onAlert = _onAlert;
    });
  }

  void _onAlert(String alertType) {
    if (!mounted) return;
    if (alertType == 'stuck') {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Row(
            children: [
              Icon(Icons.block, color: Colors.white),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Robot is STUCK — check for obstacles!',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
          backgroundColor: Colors.red[700],
          duration: const Duration(seconds: 8),
          action: SnackBarAction(
            label: 'Control',
            textColor: Colors.white,
            onPressed: () => setState(() => _selectedIndex = 1),
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: IndexedStack(
        index: _selectedIndex,
        children: _pages,
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _selectedIndex,
        onDestinationSelected: (i) => setState(() => _selectedIndex = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.map_outlined),
            selectedIcon: Icon(Icons.map),
            label: 'Map',
          ),
          NavigationDestination(
            icon: Icon(Icons.tune_outlined),
            selectedIcon: Icon(Icons.tune),
            label: 'Control',
          ),
        ],
      ),
    );
  }
}
