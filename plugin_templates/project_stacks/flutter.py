"""Flutter mobile + web stub stack template."""

STACK_TEMPLATE = {
    "name": "flutter",
    "display_name": "Flutter (Mobile + Web)",
    "template_dir": None,
    "tech_stack": {
        "language": "dart",
        "framework": "flutter",
        "database": "none",
        "css": None,
        "package_manager": "pub",
        "runtime": "dart-vm",
        "auth": "none",
        "testing": "flutter_test",
    },
    "base_directory_structure": [
        "lib/",
        "lib/main.dart",
        "lib/app.dart",
        "lib/screens/",
        "lib/screens/home_screen.dart",
        "lib/widgets/",
        "lib/models/",
        "lib/services/",
        "lib/utils/",
        "lib/constants.dart",
        "lib/theme.dart",
        "test/",
        "test/widget_test.dart",
        "assets/",
        "assets/images/",
        "android/",
        "ios/",
        "web/",
        ".env.example",
    ],
    "base_dependencies": {
        "runtime": [
            "flutter",
            "go_router: ^13.0.0",
            "provider: ^6.1.2",
            "http: ^1.2.0",
            "shared_preferences: ^2.2.2",
            "cached_network_image: ^3.3.0",
        ],
        "dev": [
            "flutter_test",
            "flutter_lints: ^4.0.0",
            "mockito: ^5.4.4",
        ],
    },
    "run_commands": {
        "install": "flutter pub get",
        "dev": "flutter run",
        "build_apk": "flutter build apk",
        "build_web": "flutter build web",
        "test": "flutter test",
        "analyze": "flutter analyze",
    },
    "env_vars": [
        {
            "name": "API_BASE_URL",
            "description": "Backend API base URL",
            "example_value": "https://api.example.com",
            "required": False,
        },
    ],
    "docker_services": [],
    "blueprint_hints": {
        "state": "Provider / Riverpod / BLoC",
        "navigation": "GoRouter",
        "http": "Dart http package or Dio",
        "local_storage": "SharedPreferences or Hive",
        "testing": "flutter_test + mockito",
        "note": "Flutter requires Dart SDK and Flutter SDK installed. Run `flutter doctor` to verify environment.",
    },
    "pubspec_template": """name: {project_name}
description: {description}
version: 1.0.0+1
publish_to: none

environment:
  sdk: '>=3.0.0 <4.0.0'
  flutter: '>=3.19.0'

dependencies:
  flutter:
    sdk: flutter
  go_router: ^13.0.0
  provider: ^6.1.2
  http: ^1.2.0
  shared_preferences: ^2.2.2
  cached_network_image: ^3.3.0

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^4.0.0
  mockito: ^5.4.4

flutter:
  uses-material-design: true
  assets:
    - assets/images/
""",
}
