package com.procurepilot.procurepilot_mobile

import io.flutter.embedding.android.FlutterFragmentActivity

// local_auth requires its host activity to extend FlutterFragmentActivity, not the plain
// FlutterActivity — without this, biometric authentication fails at runtime on Android even when
// the device supports biometrics and has credentials enrolled (PR review finding, PR #17/#19).
class MainActivity : FlutterFragmentActivity()
